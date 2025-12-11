document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', ()=>{
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

        btn.classList.add('active');
        const tabId = btn.dataset.tab + '-tab';
        document.getElementById(tabId).classList.add('active');
    });
});
async function viewProject(projectId) {
    try {
        const response = await fetch(`/api/project-details/${projectId}`);
        const project = await response.json();
        if (!response.ok){
            alert('Error loading project details');
            return;
        }
        const reviewHTML = `
        <div class="review-header">
            <h2>${project.name}</h2>
            <p>Submitted by: User</p>
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
                    <div class="info-value">${project.approved_hours}</div>
                </div>
                ${project.languages ?`
                    <div class="info-item">
                        <div class="info-label">Languages</div>
                        <div class="info-value">${project.languages}</div>
                    </div>
                ` : ''}
            </div>
            <p><strong>Description:</strong>${project.detail || 'No Description'}</p>
        </div>
        ${project.summary ?`
            <div class="review-section">
                <h3>Project Summary</h3>
                <p>${project.summary}</p>
            </div>
            ` : ''}
        
        ${project.screenshot_url ? `
            <div class="review-section">
                <h3>Screenshot</h3>
                <img src="${project.screenshot_url}" alt="Project Screenshot" class="project-screenshot">
            </div>` : ''}
            
        ${project.github_url || project.demo_url ? `
            <div class="review-section">
                <h3>Links</h3>
                <ul class="link-list">
                    ${project.github_url ? `<li><a href="${project.github_url}" target="_blank">Github Repository </a></li>` : ''}
                    ${project.demo_url ? `<li><a href=${project.demo_url}" target="_blank">Live Demo </a></li>` : ''}
                </ul>
            </div> ` : ''}
        
        ${project.comments && project.comments.length > 0 ? `
            <div class="review-section">
                <h3>Previous Comments</h3>
                ${project.comments.map(comment => `
                    <div class="info-item" style="margin-bottom: 10px;">
                        <div class="info-label">${comment.admin_name}- ${comment.created_at}</div>`
                    ).join('')}
                    </div>
                    ` : ''}
                    <div class="review-form">
                        <h3>Review Project</h3>
                        <form id="review-form-${projectId}" onsubmit="submitReview(event, ${projectId})">
                            <div class="form-group">
                                <label for="approved-hours-${projectId}"> Approved Hours</label>
                                <input type="text" id="approved-hours-${projectId}" step="0.01" min="0" value="${project.approved_hours}" required>
                            </div>
                            <div class="form-group">
                                <label for="theme-${projectId}">Theme/Category</label>
                                <input type="text" id="theme-${projectId}">value="${project.theme || ''}" placeholder="e.g., Web Development, Game, AI>
                            </div>
                            <div class="form-group">
                                <label for="status-${projectId}">Status</label>
                                <select id="status-${projectId}" required>
                                    <option value="in_review" ${project.status==='in_review' ? 'selected': ''}>In Review</option>
                                    <option value="approved" ${project.status === 'approved' ? 'selected': ''}>Approved</option>
                                    <option value="rejected" ${project.status === 'rejected' ? 'selected': ''}>Rejected</option>
                                </select>
                            </div>
                            
                            <div class="form-group">
                                <label for="comment-${projectId}">Add Comment</label>
                                <textarea id="comment-${projectId}" rows="4" placeholder="Leave feedback for the particpant..."></textarea>
                            </div>
                            <div class="tiles-input-group">
                                <input type="number" id="tiles-${projectId}" min="0" placeholder="Award tiles to participant" value="0">
                                <button type="button" onclick="awardTiles(${projectId})">Award Tiles </button>
                            </div>
                            <div class="form-actions">
                                <button type="submit" class="btn-approve">Save Review</button>
                                <button type="button" class="btn-reject" onclick="quickReject(${projectId})">Quick Reject</button>
                            </div>
                        </form>
                    </div>
                `;

                document.getElementById('review-content').innerHTML = reviewHTML;
                document.getElementById('review-modal').classList.remove('hidden');
    } catch (e) {
        alert('Error Loading Project Details');
        console.error(e);
    }
}
async function submitReview(event, projectId) {
        event.preventDefault();
        const approvedHours = document.getElementById(`approved-hours-${projectId}`).value;
        const theme = document.getElementById(`theme-${projectId}`).value;
        const status = document.getElementById(`status-${projectId}`).value;
        const comment = document.getElementById(`comment-${projectId}`).value;

        try {
            const reviewResponse = await fetch(`/admin/api/review-project/${projectId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    approved_hours: approvedHours,
                    theme: theme,
                    status: status
                })
            });
            if (!reviewResponse.ok){
                alert('Error Updating project review!');
                return;
            }
            if (comment.trim()){
                const commentResponse = await fetch(`/admin/api/comment-project/${projectId}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        comment: comment
                    })
                });
                if (!commentResponse.ok){
                    console.error('Error addibng comment');
                }
            }
            alert('Review saved successfully!')
            closeReviewModal();
            location.reload(); 
        } catch (e) {
            alert('Error submitting review');
            console.error(e);
        }
}
async function awardTiles(projectId) {
    const tiles_amount = document.getElementById(`tiles-${projectId}`).value;
    if (!tilesAmount || tilesAmount <= 0){
        alert('Please enter a valid tiles amount');
        return;
    }
    if (!confirm(`Award ${tilesAmount} tiles to this user?`)) return;
    try {
        const response = await fetch(`/admin/api/award-tiles/${projectId}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({tiles: parseInt(tilesAmount)})
        });

        if (response.ok){
            const data = await response.json();
            alert(`Tiles awarded! New Balance: ${data.new_balance}`);
            document.getElementById(`tiles-${projectId}`).value=0;
        } else {
            alert('Error awarding tiles!');
        }
    } catch (e) {
        alert('Error awarding tiles!');
        console.error(e);
    }
}
async function quickReject(projectId) {
    const comment = prompt('Please provide a reason for rejetion!');
    if (!comment) reutrn;

    try {
        const reviewResponse = await fetch(`/admin/api/review-project/${projectId}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                status: 'rejected',
                approved_hours: 0
            })
        });
        if (!reviewResponse.ok){
            alert('Error Rejecting project!');
            return;
        }
        await fetch(`/admin/api/comment-project/${projectId}`, {
            method: 'POST',
            headers: {'Content-Type' : 'application/json'},
            body: JSON.stringify({'comment': comment})
        });
        alert('Projecct rejected');
        closeReviewModal();
        location.reload();

    } catch (e) {
        alert('Error Rejecting Project');
        console.error(e);
    }  
}
async function assignToSelf(projectId) {
    if (!confirm('Assign this project to yourself?')) return;
    try {
        const response = await fetch (`/admin/api/assign-project/${projectId}`, {
            method: 'POST',
            headers: {'Content-Type' : 'application/json'}
        });
        if (response.ok) {
            alert('Project assigned to you!');
            location.reload()
        } else {
            alert ('Error Assigning project!');
        }
    } catch (e) {
        alert('Error assigning project');
        console.error(e);
    }    
}
function openThemeModal(){
    document.getElementById('theme-modal').classList.remove('hidden');
}
function closeThemeModal(){
    document.getElementById('theme.modal').classList.add('hidden');
    document.getElementById('theme-form').reset();
}
async function submitTheme(event){
    event.preventDefault();
    const name = document.getElementById('theme-name').value;
    const description = document.getElementById('theme-description').value;
    try {
        const response = await fetch(`/admin/api/add-theme`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name, description})
        });
        if (response.ok){
            alert('Theme added successfully!');
            closeThemeModal();
            location.reload()
        } else {
            alert('Error adding theme!');
        }
    } catch(e){
        alert('Error adding theme!');
    }
}
async function manageThemes() {
    try {
        const response = await fetch('/api/themes');
        const data = await response.json()
        const themesList = document.getElementById('themes-list');
        if (data.themes && data.themes.length > 0){
            themesList.innerHTML = data.themes.map(theme => `
                <div class="theme-list-item">
                    <div>
                        <h4>${theme.name}</h4>
                        <p>${theme.description || 'No Description'}</p>
                    </div>
                    <button class="delete-theme-btn onclick="deleteTheme(${theme.id})">Delete Theme</button>
                </div>
                `).join('');
        } else {
            themesList.innerHTML=`<p style="text-align: center; color: #666;">No themes yet</p>`;
        }
        document.getElementById('themes-list-modal').classList.remove('hidden');
    } catch (e){
        alert('Error Loading themes');
        console.error(e);
    }
}
function closeThemesListModal(){
    document.getElementById('themes-list-modal').classList.add('hidden');
}
async function deleteTheme(themeId) {
    if (!confirm('Delete this theme?')) return;

    try {
        const response = await fetch(`/admin/api/delete-theme/${themeId}`, {
            method: 'DELETE'
        });
        if (response.ok){
            alert('Theme deleted!');
            manageThemes();
        } else {
            alert('Error deleting theme');
        }
    } catch (e){
        alert('Error deleting theme');
        console.error(e);
    }
}
function closeReviewModal(){
    document.getElementById('review-modal').classList.add('hidden');
}
document.getElementById('review-modal')?.addEventListener('click', (e)=>{
    if (e.targetid === 'review-modal'){
        closeReviewModal()
    }
});
document.getElementById('theme-modal')?.addEventListener('click', (e)=>{
    if (e.targetid === 'theme-modal'){
        closeThemeModal()
    }
});
document.getElementById('themes-list-modal')?.addEventListener('click', (e)=>{
    if (e.targetid === 'themes-list-modal'){
        closeThemesListModal()
    }
});