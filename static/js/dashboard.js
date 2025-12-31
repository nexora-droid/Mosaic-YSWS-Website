let currentProjectId = null;

//warning
function showHackatimePopup() {
    const modal = document.getElementById('hackatime-modal');
    if (modal) modal.classList.remove('hidden');
}

function closeHackatimePopup() {
    const modal = document.getElementById('hackatime-modal');
    if (modal) modal.classList.add('hidden');
}

//theme
async function loadCurrentTheme() {
    try {
        const response = await fetch('/api/themes');
        const data = await response.json();
        
        if (data.themes && data.themes.length > 0) {
            document.getElementById('theme-name').textContent = data.themes[0].name;
        } else {
            document.getElementById('theme-name').textContent = 'No active theme';
        }
    } catch (e) {
        console.error('Error loading theme:', e);
        document.getElementById('theme-name').textContent = 'Error loading';
    }
}

// Select Project
async function selectProject(projectId) {
    currentProjectId = projectId;
    
    document.querySelectorAll('.project-card').forEach(card => {
        card.classList.remove('selected');
    });
    document.querySelector(`[data-project-id="${projectId}"]`)?.classList.add('selected');
    
    const emptyState = document.getElementById('empty-state');
    const projectInfo = document.getElementById('project-info');
    
    emptyState.style.display = 'none';
    projectInfo.style.display = 'block';
    projectInfo.innerHTML = '<div style="text-align: center; padding: 40px;"><div style="font-size: 40px; color: #235789;">Loading...</div></div>';
    
    try {
        const response = await fetch(`/api/project-details/${projectId}`);
        const project = await response.json();
        
        if (!response.ok) {
            await showAlert('Error loading project details', 'error');
            return;
        }
        
        renderProjectDetails(project);
        
    } catch (e) {
        console.error('Error loading project:', e);
        await showAlert('Error loading project details', 'error');
    }
}

function renderProjectDetails(project) {
    const projectInfo = document.getElementById('project-info');
    
    const statusDisplay = project.status === 'approved' ? 'Sold' :
                         project.status === 'rejected' ? 'Refunded' :
                         project.status === 'draft' ? 'Building' :
                         project.status;
    
    // Only show delete button if status is 'draft' not when in review or sold
    const showDelete = project.status === 'draft';
    
    let html = `
        <div class="project-detail-item">
            <div class="detail-label">Github</div>
            <div class="detail-value">
                ${project.github_url ? 
                    `<a href="${project.github_url}" target="_blank">${project.github_url}</a>` : 
                    'N/A. Add a link while submitting!'}
            </div>
        </div>
        
        <div class="project-detail-item">
            <div class="detail-label">Demo URL</div>
            <div class="detail-value">
                ${project.demo_url ? 
                    `<a href="${project.demo_url}" target="_blank">${project.demo_url}</a>` : 
                    'N/A. Add a link while submitting!'}
            </div>
        </div>
        
        <div class="project-detail-item">
            <div class="detail-label">Hours Spent</div>
            <div class="detail-value">${project.raw_hours || 0} hrs</div>
        </div>
        
        <div class="project-detail-item">
            <div class="detail-label">Status</div>
            <div class="detail-value">
                <span class="project-status status-${project.status}">${statusDisplay}</span>
            </div>
        </div>
        
        ${project.comments && project.comments.length > 0 ? `
            <div class="project-detail-item">
                <div class="detail-label">Reviewer Comments</div>
                <div class="detail-value">
                    <div class="comment-list">
                        ${project.comments.map(comment => `
                            <div class="comment-item">
                                <div class="comment-author">${comment.admin_name}</div>
                                <div class="comment-text">${comment.comment}</div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            </div>
        ` : `
            <div class="project-detail-item">
                <div class="detail-label">Reviewer Comments</div>
                <div class="detail-value">No Comments on your project yet!</div>
            </div>
        `}
        
        <div class="project-actions">
            ${project.status === 'draft' ? `
                <button class="btn-submit" onclick="openSubmitForm('${project.id}')">
                    Submit for Review
                </button>
            ` : ''}
            ${showDelete ? `
                <button class="btn-delete" onclick="deleteProject('${project.id}')">
                    Delete
                </button>
            ` : ''}
        </div>
    `;
    
    projectInfo.innerHTML = html;
}

window.deleteProject = async function(projectId) {
    const confirmed = await showConfirm('Are you sure you want to delete this project? This action cannot be undone.');
    if (!confirmed) return;
    
    try {
        const response = await fetch(`/api/delete-project/${projectId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            await showAlert('Project deleted successfully!', 'success');
            window.location.reload();
        } else {
            const error = await response.json();
            await showAlert(error.error || 'Error deleting project', 'error');
        }
    } catch (e) {
        console.error('Error deleting project:', e);
        await showAlert('Error deleting project', 'error');
    }
};

window.openSubmitForm = function(projectId) {
    const submitProjectId = document.getElementById("submit-project-id");
    const submitOverlay = document.getElementById("submit-overlay");
    
    if (submitProjectId) submitProjectId.value = projectId;
    if (submitOverlay) submitOverlay.classList.remove("hidden");
};
//inti
window.addEventListener("DOMContentLoaded", () => {
    const addProjectBtn = document.getElementById("add-project-btn");
    const addProjectForm = document.getElementById("add-project-form");
    const overlay = document.getElementById("overlay");
    const closeOverlay = document.getElementById("close-overlay");
    const hackProject = document.getElementById("hack-project");
    const hoursPreview = document.getElementById("project-hours");
    const screenshotInput = document.getElementById("screenshot-url");
    const screenshotPreview = document.getElementById("screenshot-preview");
    const submitOverlay = document.getElementById("submit-overlay");
    const closeSubmit = document.getElementById("close-submit");
    const submitForm = document.getElementById("submit-project-form");
    
    // Load current theme
    loadCurrentTheme();
    
    //auto select proj
    const firstProject = document.querySelector('.project-card');
    if (firstProject) {
        const projectId = firstProject.getAttribute('data-project-id');
        selectProject(projectId);
    }
    
    function resetAddForm() {
        addProjectForm.reset();
        hoursPreview.textContent = "";
    }
    
    addProjectForm?.addEventListener("submit", async(e) => {
        e.preventDefault();
        const projectName = document.getElementById("project-name").value.trim();
        const projectDetail = document.getElementById("project-detail").value;
        const hackProjectValue = document.getElementById("hack-project").value;
        
        if (!projectName) {
            await showAlert("Project name cannot be empty", 'warning');
            return;
        }
        
        try {
            const response = await fetch('/api/add-project', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    name: projectName,
                    detail: projectDetail,
                    hack_project: hackProjectValue
                })
            });
            
            if (!response.ok) {
                const err = await response.json();
                await showAlert('Error Adding Project: ' + (err.error || 'Unknown Error'), 'error');
                return;
            }
            
            await showAlert('Project added successfully!', 'success');
            window.location.reload();
        } catch (e) {
            await showAlert('Error adding project.', 'error');
            console.error(e);
        }
    });
    
    submitForm?.addEventListener("submit", async(e) => {
        e.preventDefault();
        const projectId = document.getElementById("submit-project-id").value;
        const screenshotUrl = document.getElementById("screenshot-url").value;
        const githubUrl = document.getElementById("github-url").value;
        const demoUrl = document.getElementById("demo-url").value;
        const languages = document.getElementById("languages").value;
        const summary = document.getElementById("summary").value;
        
        try {
            const response = await fetch(`/api/submit-project/${projectId}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    screenshot_url: screenshotUrl,
                    github_url: githubUrl,
                    demo_url: demoUrl,
                    languages: languages,
                    summary: summary,
                })
            });
            
            if (response.ok) {
                await showAlert('Project Submitted Successfully!', 'success');
                submitOverlay.classList.add("hidden");
                window.location.reload();
            } else {
                const err = await response.json();
                await showAlert('Error: ' + (err.error || 'Could not be submitted!'), 'error');
            }
        } catch (e) {
            await showAlert("Error submitting project!", 'error');
            console.error(e);
        }
    });
    
    //screenshot
    screenshotInput?.addEventListener("input", () => {
        const url = screenshotInput.value;
        if (url) {
            screenshotPreview.innerHTML = `<img src="${url}" alt="Screenshot preview" onerror="this.style.display='none'">`;
        } else {
            screenshotPreview.innerHTML = "";
        }
    });
    
    //project hrs
    hackProject?.addEventListener("change", async() => {
        const projectName = hackProject.value;
        if (!projectName) {
            hoursPreview.textContent = '';
            return;
        }
        
        hoursPreview.textContent = "Fetching hours...";
        
        try {
            const params = new URLSearchParams({project_name: projectName});
            const response = await fetch('/api/project-hours?' + params.toString());
            
            if (response.ok) {
                const data = await response.json();
                
                if (data.hours !== undefined) {
                    hoursPreview.textContent = `Hours Spent: ${(data.hours ?? 0).toFixed(2)} hr(s)`;
                } else if (data.message) {
                    hoursPreview.textContent = `Note: ${data.message}`;
                } else {
                    hoursPreview.textContent = 'Hours Spent: 0.00 hr(s)';
                }
            } else {
                hoursPreview.textContent = 'Unable to fetch hours';
            }
        } catch (e) {
            console.error('Error fetching hours:', e);
            hoursPreview.textContent = "Network error";
        }
    });
    
    submitOverlay?.addEventListener("click", (e) => {
        if (e.target === submitOverlay) {
            submitOverlay.classList.add("hidden");
        }
    });
    
    closeSubmit?.addEventListener("click", () => {
        submitOverlay.classList.add("hidden");
    });
    
    overlay?.addEventListener("click", (e) => {
        if (e.target === overlay) {
            overlay.classList.add("hidden");
            resetAddForm();
        }
    });
    
    closeOverlay?.addEventListener("click", () => {
        overlay.classList.add("hidden");
        resetAddForm();
    });
    
    addProjectBtn?.addEventListener("click", () => {
        overlay.classList.remove("hidden");
    });
});

//refresh tiles
async function refreshTilesBalance() {
    try {
        const response = await fetch('/dashboard');
        if (response.ok) {
            const html = await response.text();
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            
            const tilesCard = doc.querySelector('.tiles-balance');
            if (tilesCard) {
                const currentCard = document.querySelector('.tiles-balance');
                if (currentCard && currentCard.textContent !== tilesCard.textContent) {
                    currentCard.innerHTML = tilesCard.innerHTML;
                    currentCard.style.transform = 'scale(1.05)';
                    setTimeout(() => {
                        currentCard.style.transform = 'scale(1)';
                    }, 300);
                }
            }
        }
    } catch (e) {
        console.error('Error refreshing tiles balance:', e);
    }
}

setInterval(refreshTilesBalance, 10000);
window.addEventListener('focus', refreshTilesBalance);