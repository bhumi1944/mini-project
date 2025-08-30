import os
from datetime import datetime
from flask import render_template, url_for, flash, redirect, request, abort, send_from_directory
from flask_login import login_user, current_user, logout_user, login_required
from werkzeug.utils import secure_filename

from app import app, db
from forms import (
    RoleSelectionForm, LoginForm, RegistrationForm, UpdateProfileForm,
    UploadDocumentForm, EditDocumentForm, CollaborationForm
)
from models import User, Document, Notification, Collaboration
from utils import allowed_file, save_file, get_file_size, get_file_type, create_notification, has_permission


@app.route('/')
def index():
    """Home page route."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route('/role-selection', methods=['GET', 'POST'])
def role_selection():
    """Role selection page for registration."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = RoleSelectionForm()
    
    if form.validate_on_submit():
        role = request.form.get('role')
        if role in ['student', 'professor', 'company']:
            return redirect(url_for('register', role=role))
        else:
            flash('Invalid role selected.', 'danger')
    
    return render_template('role_selection.html', form=form)


@app.route('/register/<role>', methods=['GET', 'POST'])
def register(role):
    """Registration page for specific roles."""
    if role not in ['student', 'professor', 'company']:
        return redirect(url_for('role_selection'))
    
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = RegistrationForm()
    
    # Remove irrelevant fields based on role
    if role == 'student':
        del form.field
        del form.company_name
    elif role == 'professor':
        del form.company_name
    elif role == 'company':
        del form.college
        del form.date_of_birth
        del form.field
    
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data,
            role=role
        )
        user.set_password(form.password.data)
        
        # Set role-specific fields
        if role == 'student' or role == 'professor':
            user.college = form.college.data
            user.date_of_birth = form.date_of_birth.data
        
        if role == 'professor':
            user.field = form.field.data
        
        if role == 'company':
            user.company_name = form.company_name.data
        
        db.session.add(user)
        db.session.commit()
        
        flash(f'Your account has been created! You can now log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html', form=form, role=role)


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = LoginForm()
    
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Login unsuccessful. Please check your email and password.', 'danger')
    
    return render_template('login.html', form=form)


@app.route('/logout')
def logout():
    """User logout."""
    logout_user()
    return redirect(url_for('index'))


@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard."""
    user_documents = Document.query.filter_by(user_id=current_user.id).order_by(Document.uploaded_at.desc()).all()
    
    # Get documents shared with the user
    collaborations = Collaboration.query.filter_by(user_id=current_user.id).all()
    shared_documents = [collab.document for collab in collaborations]
    
    # Get recent notifications
    notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).order_by(Notification.created_at.desc()).limit(5).all()
    
    return render_template(
        'dashboard.html', 
        user_documents=user_documents, 
        shared_documents=shared_documents,
        notifications=notifications,
        Document=Document
    )


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """User profile page."""
    form = UpdateProfileForm(current_user.username, current_user.email)
    
    # Remove irrelevant fields based on role
    if current_user.role == 'student':
        del form.field
        del form.company_name
    elif current_user.role == 'professor':
        del form.company_name
    elif current_user.role == 'company':
        del form.college
        del form.field
    
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.email = form.email.data
        
        if current_user.role == 'student' or current_user.role == 'professor':
            current_user.college = form.college.data
        
        if current_user.role == 'professor':
            current_user.field = form.field.data
        
        if current_user.role == 'company':
            current_user.company_name = form.company_name.data
        
        # Handle profile image upload
        if form.profile_image.data:
            try:
                filename, file_path = save_file(form.profile_image.data, 'static/uploads')
                current_user.profile_image = filename
            except Exception as e:
                flash(f'Error uploading profile image: {str(e)}', 'danger')
        
        db.session.commit()
        flash('Your profile has been updated!', 'success')
        return redirect(url_for('profile'))
    
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.email.data = current_user.email
        
        if current_user.role == 'student' or current_user.role == 'professor':
            form.college.data = current_user.college
        
        if current_user.role == 'professor':
            form.field.data = current_user.field
        
        if current_user.role == 'company':
            form.company_name.data = current_user.company_name
    
    # Get recent documents for the profile page
    documents = Document.query.filter_by(user_id=current_user.id).order_by(Document.uploaded_at.desc()).limit(5).all()
    
    return render_template('profile.html', form=form, documents=documents, Document=Document)


@app.route('/upload-document', methods=['GET', 'POST'])
@login_required
def upload_document():
    """Upload a new document."""
    form = UploadDocumentForm()
    
    if form.validate_on_submit():
        if form.document.data and allowed_file(form.document.data.filename):
            try:
                # Save the file
                filename, file_path = save_file(form.document.data, 'static/uploads/documents')
                
                # Create document record
                document = Document(
                    title=form.title.data,
                    description=form.description.data,
                    file_path=filename,
                    file_type=get_file_type(form.document.data.filename),
                    file_size=get_file_size(file_path),
                    is_public=form.is_public.data,
                    user_id=current_user.id
                )
                
                db.session.add(document)
                db.session.commit()
                
                flash('Your document has been uploaded!', 'success')
                return redirect(url_for('dashboard'))
            
            except Exception as e:
                flash(f'Error uploading document: {str(e)}', 'danger')
        else:
            flash('Invalid file type. Please upload a valid document.', 'danger')
    
    return render_template('upload_document.html', form=form, Document=Document)

@app.route('/document/<int:document_id>')
@login_required
def view_document(document_id):
    """View a document."""
    document = Document.query.get_or_404(document_id)
    
    # Check if user has permission to view
    if not document.is_public and document.user_id != current_user.id:
        if not has_permission(current_user, document, 'view'):
            abort(403)
    
    # Get collaborators
    collaborators = User.query.join(Collaboration).filter(
        Collaboration.document_id == document.id
    ).all()
    
    return render_template('document_view.html', document=document, collaborators=collaborators, Document=Document)


@app.route('/document/<int:document_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_document(document_id):
    """Edit a document."""
    document = Document.query.get_or_404(document_id)
    
    # Check if user has permission to edit
    if document.user_id != current_user.id and not has_permission(current_user, document, 'edit'):
        abort(403)
    
    form = EditDocumentForm()
    
    if form.validate_on_submit():
        document.title = form.title.data
        document.description = form.description.data
        document.is_public = form.is_public.data
        document.last_modified = datetime.utcnow()
        
        db.session.commit()
        
        flash('Document has been updated!', 'success')
        return redirect(url_for('view_document', document_id=document.id))
    
    elif request.method == 'GET':
        form.title.data = document.title
        form.description.data = document.description
        form.is_public.data = document.is_public
    
    return render_template('edit_document.html', form=form, document=document, Document=Document)



@app.route('/document/<int:document_id>/download')
@login_required
def download_document(document_id):
    """Download a document."""
    document = Document.query.get_or_404(document_id)
    
    # Check if user has permission to download
    if not document.is_public and document.user_id != current_user.id:
        if not has_permission(current_user, document, 'view'):
            abort(403)
    
    return send_from_directory(
        os.path.join(app.root_path, 'static/uploads/documents'),
        document.file_path,
        as_attachment=True,
        download_name=f"{document.title}.{document.file_type}"
    )


@app.route('/document/<int:document_id>/delete', methods=['POST'])
@login_required
def delete_document(document_id):
    """Delete a document."""
    document = Document.query.get_or_404(document_id)
    
    # Only the owner can delete
    if document.user_id != current_user.id:
        abort(403)
    
    # Delete the file
    try:
        os.remove(os.path.join(app.root_path, 'static/uploads/documents', document.file_path))
    except:
        # If file doesn't exist, continue with deletion from DB
        pass
    
    # Delete related collaborations
    Collaboration.query.filter_by(document_id=document.id).delete()
    
    # Delete the document record
    db.session.delete(document)
    db.session.commit()
    
    flash('Document has been deleted!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/document/<int:document_id>/collaborate', methods=['GET', 'POST'])
@login_required
def collaborate(document_id):
    """Add collaborators to a document."""
    document = Document.query.get_or_404(document_id)
    
    # Only the owner can add collaborators
    if document.user_id != current_user.id:
        abort(403)
    
    form = CollaborationForm()
    
    if form.validate_on_submit():
        collaborator = User.query.filter_by(email=form.collaborator_email.data).first()
        
        # Check if user is already a collaborator
        existing_collab = Collaboration.query.filter_by(
            document_id=document.id,
            user_id=collaborator.id
        ).first()
        
        if existing_collab:
            existing_collab.permission = form.permission.data
            db.session.commit()
            flash(f'Collaboration with {collaborator.username} has been updated!', 'success')
        else:
            # Create new collaboration
            collaboration = Collaboration(
                document_id=document.id,
                user_id=collaborator.id,
                permission=form.permission.data
            )
            
            db.session.add(collaboration)
            db.session.commit()
            
            # Create notification for the collaborator
            create_notification(
                collaborator.id,
                f"{current_user.username} has shared a document '{document.title}' with you.",
                related_document_id=document.id,
                related_user_id=current_user.id
            )
            
            flash(f'Document has been shared with {collaborator.username}!', 'success')
        
        return redirect(url_for('view_document', document_id=document.id))
    
    # Get existing collaborators
    collaborations = Collaboration.query.filter_by(document_id=document.id).all()
    collaborators = [(collab, User.query.get(collab.user_id)) for collab in collaborations]
    
    return render_template('collaborate.html', form=form, document=document, collaborators=collaborators, Document=Document)


@app.route('/document/<int:document_id>/remove-collaborator/<int:user_id>', methods=['POST'])
@login_required
def remove_collaborator(document_id, user_id):
    """Remove a collaborator from a document."""
    document = Document.query.get_or_404(document_id)
    
    # Only the owner can remove collaborators
    if document.user_id != current_user.id:
        abort(403)
    
    collaboration = Collaboration.query.filter_by(
        document_id=document.id,
        user_id=user_id
    ).first_or_404()
    
    collaborator = User.query.get(user_id)
    
    db.session.delete(collaboration)
    db.session.commit()
    
    # Create notification for the collaborator
    create_notification(
        collaborator.id,
        f"{current_user.username} has removed you from the document '{document.title}'.",
        related_document_id=document.id,
        related_user_id=current_user.id
    )
    
    flash(f'Collaborator has been removed!', 'success')
    return redirect(url_for('collaborate', document_id=document.id))


@app.route('/notifications')
@login_required
def notifications():
    """User notifications page."""
    unread_notifications = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).order_by(Notification.created_at.desc()).all()
    
    read_notifications = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=True
    ).order_by(Notification.created_at.desc()).all()
    
    return render_template(
        'notifications.html',
        unread_notifications=unread_notifications,
        read_notifications=read_notifications
    )


@app.route('/notification/<int:notification_id>/mark-read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """Mark a notification as read."""
    notification = Notification.query.get_or_404(notification_id)
    
    # Ensure the notification belongs to the current user
    if notification.user_id != current_user.id:
        abort(403)
    
    notification.is_read = True
    db.session.commit()
    
    return redirect(url_for('notifications'))


@app.route('/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    """Mark all notifications as read."""
    Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).update({Notification.is_read: True})
    
    db.session.commit()
    
    flash('All notifications marked as read!', 'success')
    return redirect(url_for('notifications'))


@app.errorhandler(404)
def page_not_found(e):
    """404 error handler."""
    return render_template('404.html'), 404


@app.errorhandler(403)
def forbidden(e):
    """403 error handler."""
    return render_template('403.html'), 403


@app.errorhandler(500)
def internal_server_error(e):
    """500 error handler."""
    return render_template('500.html'), 500
