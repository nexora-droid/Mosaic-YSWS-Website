// Load users on page load
let selectedUserId = null;
let allUsers = [];
let currentFilter = 'all';

document.addEventListener('DOMContentLoaded', async () => {
    await loadAllUsers();
    await loadThemes();
    await loadStats();
});

async function loadAllUsers() {
    const usersList = document.getElementById('users-list');
    usersList.innerHTML = `
        <div style="text-align: center; padding: 40px;">
            <i class="fas fa-spinner fa-spin" style="font-size: 40px; color: var(--blue-accent);"></i>
            <p style="margin-top: 15px; color: #666;">Loading users...</p>
        </div>
    `;
    
    try {
        const response = await fetch(`/api/all-users?filter=${currentFilter}`);
        const data = await response.json();
        
        if (!response.ok) {
            console.error('Error loading users:', data.error);
            usersList.innerHTML = `
                <div style="text-align: center; padding: 20px; color: #D32F2F;">
                    <i class="fas fa-exclamation-circle" style="font-size: 40px;"></i>
                    <p style="margin-top: 10px;">Error loading users</p>
                </div>
            `;
            return;
        }
        
        allUsers = data.users || [];
        renderUsers(allUsers);
        
    } catch (e) {
        console.error('Error loading users:', e);
        usersList.innerHTML = `
            <div style="text-align: center; padding: 20px; color: #D32F2F;">
                <i class="fas fa-exclamation-circle" style="font-size: 40px;"></i>
                <p style="margin-top: 10px;">Network error</p>
            </div>
        `;
    }
}
function renderUsers(users){
    const usersList = document.getElementById('users-list');
    
    if (users.length === 0) {
        usersList.innerHTML = '<p style="text-align: center; color: #666; padding: 20px;">No users found</p>';
        return;
    }
    
    usersList.innerHTML = users.map(user => `
        <div class="user-item" data-user-id="${user.id}" data-user-name="${(user.name || '').toLowerCase()}" onclick="selectUser('${user.id}')">
            <div class="user-header">
                <h4>${user.name || 'Unknown User'}</h4>
                ${user.draft_count > 0 ? '<span class="draft-badge"><i class="fas fa-file"></i></span>' : ''}
            </div>
            <div class="user-stats-mini">
                <span class="stat-mini" title="Total Projects">
                    <i class="fas fa-folder"></i>
                    ${user.total_projects}
                </span>
                ${user.draft_count > 0 ? `
                <span class="stat-mini draft" title="Draft Projects">
                    <i class="fas fa-file-alt"></i>
                    ${user.draft_count}
                </span>
                ` : ''}
                ${user.in_review_count > 0 ? `
                <span class="stat-mini review" title="In Review">
                    <i class="fas fa-clock"></i>
                    ${user.in_review_count}
                </span>
                ` : ''}
                ${user.approved_count > 0 ? `
                <span class="stat-mini approved" title="Approved">
                    <i class="fas fa-check-circle"></i>
                    ${user.approved_count}
                </span>
                ` : ''}
            </div>
            <div class="user-meta">
                <span><i class="fas fa-clock"></i> ${user.total_hours.toFixed(2)} hrs</span>
                <span><i class="fas fa-dice"></i> ${user.tiles_balance} tiles</span>
            </div>
        </div>
    `).join('');
}

function filterUsers() {
    const searchTerm = document.getElementById('user-search').value.toLowerCase();
    
    const filteredUsers = allUsers.filter(user => {
        const userName = (user.name || '').toLowerCase();
        return userName.includes(searchTerm);
    });
    
    renderUsers(filteredUsers);
}

async function applyFilter(filter) {
    currentFilter = filter;
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`[data-filter="${filter}"]`).classList.add('active');
    await loadAllUsers();
}

async function selectUser(userId) {
    selectedUserId = userId;
    
    document.querySelectorAll('.user-item').forEach(item => {
        item.classList.remove('active');
    });
    document.querySelector(`[data-user-id="${userId}"]`)?.classList.add('active');
    await loadUserProjects(userId);
}

async function loadUserProjects(userId) {
    const projectsList = document.getElementById('projects-list');
    projectsList.innerHTML = `
        <div class="empty-message">
            <i class="fas fa-spinner fa-spin" style="font-size: 50px; color: var(--blue-accent);"></i>
            <p style="margin-top: 15px;">Loading projects...</p>
        </div>
    `;
    
    try {
        const response = await fetch(`/api/user-projects/${userId}`);
        const data = await response.json();
        
        if (!response.ok) {
            await showAlert('Error loading user projects', 'error');
            projectsList.innerHTML = `
                <div class="empty-message">
                    <i class="fas fa-exclamation-circle" style="font-size: 80px; color: #D32F2F;"></i>
                    <p>Error loading projects</p>
                </div>
            `;
            return;
        }
        
        if (data.projects && data.projects.length > 0) {
            const draftProjects = data.projects.filter(p => p.status === 'draft');
            const inReviewProjects = data.projects.filter(p => p.status === 'in_review');
            const approvedProjects = data.projects.filter(p => p.status === 'approved');
            const rejectedProjects = data.projects.filter(p => p.status === 'rejected');
            
            let html = '';
            
            if (draftProjects.length > 0) {
                html += `
                    <div class="project-section">
                        <h3 class="section-title">
                            <i class="fas fa-file-alt"></i> Draft Projects (${draftProjects.length})
                        </h3>
                        ${renderProjectCards(draftProjects)}
                    </div>
                `;
            }
            if (inReviewProjects.length > 0) {
                html += `
                    <div class="project-section">
                        <h3 class="section-title">
                            <i class="fas fa-clock"></i> In Review (${inReviewProjects.length})
                        </h3>
                        ${renderProjectCards(inReviewProjects)}
                    </div>
                `;
            }
            
            if (approvedProjects.length > 0) {
                html += `
                    <div class="project-section">
                        <h3 class="section-title">
                            <i class="fas fa-check-circle"></i> Approved (${approvedProjects.length})
                        </h3>
                        ${renderProjectCards(approvedProjects)}
                    </div>
                `;
            }
            if (rejectedProjects.length > 0) {
                html += `
                    <div class="project-section">
                        <h3 class="section-title">
                            <i class="fas fa-times-circle"></i> Rejected (${rejectedProjects.length})
                        </h3>
                        ${renderProjectCards(rejectedProjects)}
                    </div>
                `;
            }
            
            projectsList.innerHTML = html;
        } else {
            projectsList.innerHTML = `
                <div class="empty-message">
                    <i class="fas fa-folder-open" style="font-size: 80px; color: var(--blue-accent); margin-bottom: 15px;"></i>
                    <p>No projects yet</p>
                </div>
            `;
        }
    } catch (e) {
        console.error('Error loading user projects:', e);
        await showAlert('Network error loading projects', 'error');
        projectsList.innerHTML = `
            <div class="empty-message">
                <i class="fas fa-exclamation-circle" style="font-size: 80px; color: #D32F2F;"></i>
                <p>Network error</p>
            </div>
        `;
    }
}
function renderProjectCards(projects) {
    const statusDisplay = {
        'draft': 'BUILDING',
        'in_review': 'IN REVIEW',
        'approved': 'APPROVED',
        'rejected': 'REJECTED'
    };
    
    return projects.map(project => {
        let submittedDate = '';
        if (project.submitted_at) {
            try {
                submittedDate = new Date(project.submitted_at).toLocaleDateString();
            } catch (e) {
                submittedDate = 'N/A';
            }
        }
        return `
        <div class="project-card-admin" onclick="viewProject('${project.id}')">
            <div class="project-card-header">
                <h3>${project.name}</h3>
                <span class="status-badge status-${project.status}">${statusDisplay[project.status] || project.status.toUpperCase()}</span>
            </div>
            <p class="project-description">${project.detail || 'No description'}</p>
            ${project.theme ? `<span class="theme-tag">${project.theme}</span>` : ''}
            <div class="project-meta-info">
                <span><i class="fas fa-clock"></i> ${project.approved_hours || 0} hrs</span>
                ${submittedDate ? `<span><i class="fas fa-calendar"></i> ${submittedDate}</span>` : ''}
            </div>
            <div class="project-actions">
                <button class="btn-review" onclick="event.stopPropagation(); viewProject('${project.id}')">
                    <i class="fas fa-eye"></i> Review
                </button>
            </div>
        </div>
        `;
    }).join('');
}

async function refreshAfterAction() {
    await Promise.all([
        loadAllUsers(),
        loadStats()
    ]);
    if (selectedUserId) {
        await loadUserProjects(selectedUserId);
    }
}

async function loadThemes() {
    const themesList = document.getElementById('themes-list');
    
    themesList.innerHTML = '<p style="text-align: center; color: #999;"><i class="fas fa-spinner fa-spin"></i> Loading...</p>';
    
    try {
        const response = await fetch('/api/themes');
        const data = await response.json();
        
        if (data.themes && data.themes.length > 0) {
            themesList.innerHTML = data.themes.map(theme => `
                <div class="theme-item-compact">
                    <h4>${theme.name}</h4>
                    ${theme.description ? `<p>${theme.description}</p>` : ''}
                    <button class="delete-theme-mini" onclick="deleteTheme('${theme.id}')">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            `).join('');
        } else {
            themesList.innerHTML = '<p style="text-align: center; color: #666;">No themes yet</p>';
        }
    } catch (e) {
        console.error('Error loading themes:', e);
        themesList.innerHTML = '<p style="text-align: center; color: #D32F2F;">Error loading themes</p>';
    }
}

async function loadStats() {
    try {
        const statIds = ['stat-total-users', 'stat-total-projects', 'stat-draft', 'stat-pending', 'stat-approved', 'stat-total-hours', 'stat-raw-hours', 'stat-total-tiles'];
        statIds.forEach(id => {
            document.getElementById(id).textContent = '...';
        });
        
        const response = await fetch('/api/admin-stats');
        const data = await response.json();
        
        if (response.ok) {
            document.getElementById('stat-total-users').textContent = data.total_users || 0;
            document.getElementById('stat-total-projects').textContent = data.total_projects || 0;
            document.getElementById('stat-draft').textContent = data.draft_projects || 0;
            document.getElementById('stat-pending').textContent = data.pending_reviews || 0;
            document.getElementById('stat-approved').textContent = data.approved_projects || 0;
            document.getElementById('stat-total-hours').textContent = data.total_hours || 0;
            document.getElementById('stat-raw-hours').textContent = data.raw_hours || 0;
            document.getElementById('stat-total-tiles').textContent = data.total_tiles_awarded || 0;
        } else {
            console.error('Error loading stats:', data.error);
            statIds.forEach(id => {
                document.getElementById(id).textContent = '-';
            });
        }
    } catch (e) {
        console.error('Error loading stats:', e);
        const statIds = ['stat-total-users', 'stat-total-projects', 'stat-draft', 'stat-pending', 'stat-approved', 'stat-total-hours', 'stat-raw-hours', 'stat-total-tiles'];
        statIds.forEach(id => {
            document.getElementById(id).textContent = '-';
        });
    }
}

async function viewProject(projectId) {
    const reviewContent = document.getElementById('review-content');
    reviewContent.innerHTML = `
        <div style="text-align: center; padding: 60px;">
            <i class="fas fa-spinner fa-spin" style="font-size: 60px; color: var(--blue-accent);"></i>
            <p style="margin-top: 20px; font-size: 18px; color: #666;">Loading project details...</p>
        </div>
    `;
    document.getElementById('review-modal').classList.remove('hidden');
    
    try {
        const response = await fetch(`/api/project-details/${projectId}`);
        const project = await response.json();
        
        if (!response.ok) {
            await showAlert('Error loading project details', 'error');
            document.getElementById('review-modal').classList.add('hidden');
            return;
        }
        const reviewHTML = `
        <div class="review-header">
            <h2>${project.name}</h2>
            <p>Submitted by: ${project.user_name}</p>
        </div>
        <div class="review-section">
            <h3>Project Information</h3>
            <div class="info-grid">
                <div class="info-item">
                    <div class="info-label">Status</div>
                    <div class="info-value">${project.status.replace('_', ' ').toUpperCase()}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">Raw Hours (Hackatime)</div>
                    <div class="info-value">${project.raw_hours}</div>
                </div>
                ${project.languages ? `
                    <div class="info-item">
                        <div class="info-label">Languages</div>
                        <div class="info-value">${project.languages}</div>
                    </div>
                ` : ''}
            </div>
            <p><strong>Description:</strong> ${project.detail || 'No Description'}</p>
        </div>
        ${project.summary ? `
            <div class="review-section">
                <h3>Project Summary</h3>
                <p>${project.summary}</p>
            </div>
        ` : ''}
        
        ${project.screenshot_url ? `
            <div class="review-section">
                <h3>Screenshot</h3>
                <img src="${project.screenshot_url}" alt="Project Screenshot" class="project-screenshot">
            </div>
        ` : ''}
            
        ${project.github_url || project.demo_url ? `
            <div class="review-section">
                <h3>Links</h3>
                <ul class="link-list">
                    ${project.github_url ? `<li><a href="${project.github_url}" target="_blank"><i class="fab fa-github"></i> Github Repository</a></li>` : ''}
                    ${project.demo_url ? `<li><a href="${project.demo_url}" target="_blank"><i class="fas fa-external-link-alt"></i> Live Demo</a></li>` : ''}
                </ul>
            </div>
        ` : ''}
        
        ${project.comments && project.comments.length > 0 ? `
            <div class="review-section">
                <h3>Previous Comments</h3>
                ${project.comments.map(comment => `
                    <div class="info-item" style="margin-bottom: 10px;">
                       <div class="info-label">${comment.admin_name} - ${new Date(comment.created_at).toLocaleString()}</div>
                        <div class="info-value">${comment.comment}</div>
                    </div>
                `).join('')}
            </div>
        ` : ''}
        <div class="review-form">
            <h3>Review Project</h3>
            <form id="review-form-${projectId}">
                <div class="form-group">
                    <label for="approved-hours-${projectId}">Approved Hours</label>
                    <input type="number" id="approved-hours-${projectId}" step="0.01" min="0" value="${project.approved_hours}" required>
                </div>
                <div class="form-group">
                    <label for="theme-${projectId}">Theme/Category</label>
                    <input type="text" id="theme-${projectId}" value="${project.theme || ''}" placeholder="e.g., Web Development, Game, AI">
                </div>
                <div class="form-group">
                    <label for="status-${projectId}">Status</label>
                    <select id="status-${projectId}" required>
                        <option value="draft" ${project.status === 'draft' ? 'selected' : ''}>Draft / Building</option>
                        <option value="in_review" ${project.status === 'in_review' ? 'selected' : ''}>In Review</option>
                        <option value="approved" ${project.status === 'approved' ? 'selected' : ''}>Approved</option>
                        <option value="rejected" ${project.status === 'rejected' ? 'selected' : ''}>Rejected</option>
                    </select>
                </div>
                
                <div class="form-group">
                    <label for="comment-${projectId}">Add Comment</label>
                    <textarea id="comment-${projectId}" rows="4" placeholder="Leave feedback for the participant..."></textarea>
                </div>
                <div class="tiles-input-group">
                    <input type="number" id="tiles-${projectId}" min="0" placeholder="Award tiles to participant" value="0">
                    <button type="button" onclick="awardTiles('${projectId}')"><i class="fas fa-gift"></i> Award Tiles</button>
                </div>
                <div class="form-actions">
                    <button type="submit" class="btn-approve"><i class="fas fa-check"></i> Save Review</button>
                    <button type="button" class="btn-reject" onclick="quickReject('${projectId}')"><i class="fas fa-times"></i> Quick Reject</button>
                </div>
            </form>
        </div>
        `;

        reviewContent.innerHTML = reviewHTML;
        document.getElementById(`review-form-${projectId}`).addEventListener('submit', (event) => {
            submitReview(event, projectId);
        });
    } catch (e) {
        await showAlert('Network error loading project details', 'error');
        document.getElementById('review-modal').classList.add('hidden');
        console.error(e);
    }
}

async function submitReview(event, projectId) {
    event.preventDefault();
    const approvedHours = document.getElementById(`approved-hours-${projectId}`).value;
    const theme = document.getElementById(`theme-${projectId}`).value;
    const status = document.getElementById(`status-${projectId}`).value;
    const comment = document.getElementById(`comment-${projectId}`).value;
    const tilesAmount = document.getElementById(`tiles-${projectId}`).value;

    try {
        const reviewResponse = await fetch(`/admin/api/review-project/${projectId}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                approved_hours: approvedHours,
                theme: theme,
                status: status,
            })
        });
        
        if (!reviewResponse.ok) {
            await showAlert('Error updating project review!', 'error');
            return;
        }
        
        if (comment.trim()) {
            const commentResponse = await fetch(`/admin/api/comment-project/${projectId}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({comment: comment})
            });
            if (!commentResponse.ok) {
                console.error('Error adding comment');
            }
        }
        
        if (tilesAmount && parseInt(tilesAmount) > 0) {
            const tilesResponse = await fetch(`/admin/api/award-tiles/${projectId}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({tiles: parseInt(tilesAmount)})
            });
            
            if (!tilesResponse.ok) {
                console.error('Error awarding tiles');
                await showAlert('Review saved but error awarding tiles!', 'warning');
                closeReviewModal();
                await refreshAfterAction();
                return;
            }
        }
    
        await showAlert('Review saved successfully!', 'success');
        closeReviewModal();
        await refreshAfterAction();
    } catch (e) {
        await showAlert('Error submitting review', 'error');
        console.error(e);
    }
}

async function awardTiles(projectId) {
    const tilesAmount = document.getElementById(`tiles-${projectId}`).value;
    if (!tilesAmount || tilesAmount <= 0) {
        await showAlert('Please enter a valid tiles amount', 'warning');
        return;
    }
    const confirmed = await showConfirm(`Award ${tilesAmount} tiles to this user?`);
    if (!confirmed) return;
    
    try {
        const response = await fetch(`/admin/api/award-tiles/${projectId}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({tiles: parseInt(tilesAmount)})
        });

        if (response.ok) {
            const data = await response.json();
            await showAlert(`Tiles awarded! New Balance: ${data.new_balance}`, 'success');
            document.getElementById(`tiles-${projectId}`).value = 0;
        } else {
            await showAlert('Error awarding tiles!', 'error');
        }
    } catch (e) {
        await showAlert('Network error awarding tiles!', 'error');
        console.error(e);
    }
}

async function quickReject(projectId) {
    const comment = prompt('Please provide a reason for rejection:');
    if (!comment) return;

    try {
        const reviewResponse = await fetch(`/admin/api/review-project/${projectId}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                status: 'rejected',
                approved_hours: 0
            })
        });
        if (!reviewResponse.ok) {
            await showAlert('Error rejecting project!', 'error');
            return;
        }
        await fetch(`/admin/api/comment-project/${projectId}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({'comment': comment})
        });
        await showAlert('Project rejected successfully', 'success');
        closeReviewModal();
        await refreshAfterAction();
    } catch (e) {
        await showAlert('Error rejecting project', 'error');
        console.error(e);
    }  
}

function openThemeModal(){
    document.getElementById('theme-modal').classList.remove('hidden');
}

function closeThemeModal() {
    document.getElementById('theme-modal').classList.add('hidden');
    document.getElementById('theme-form').reset();
}

async function submitTheme(event) {
    event.preventDefault();
    const name = document.getElementById('theme-name').value;
    const description = document.getElementById('theme-description').value;
    try {
        const response = await fetch('/admin/api/add-theme', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name, description})
        });
        if (response.ok) {
            await showAlert('Theme added successfully!', 'success');
            closeThemeModal();
            await loadThemes();
        } else {
            await showAlert('Error adding theme!', 'error');
        }
    } catch(e) {
        await showAlert('Network error adding theme!', 'error');
        console.error(e);
    }
}

async function deleteTheme(themeId) {
    const confirmed = await showConfirm('Delete this theme? This will remove it from all users\' dashboards.');
    if (!confirmed) return;

    try {
        const response = await fetch(`/admin/api/delete-theme/${themeId}`, {
            method: 'DELETE'
        });
        if (response.ok) {
            await showAlert('Theme deleted successfully!', 'success');
            await loadThemes();
        } else {
            await showAlert('Error deleting theme', 'error');
        }
    } catch (e) {
        await showAlert('Network error deleting theme', 'error');
        console.error(e);
    }
}
function closeReviewModal() {
    document.getElementById('review-modal').classList.add('hidden');
}
document.getElementById('review-modal')?.addEventListener('click', (e) => {
    if (e.target.id === 'review-modal') {
        closeReviewModal();
    }
});

document.getElementById('theme-modal')?.addEventListener('click', (e) => {
    if (e.target.id === 'theme-modal') {
        closeThemeModal();
    }
});

