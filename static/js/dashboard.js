async function loadActiveThemes(){
    try {
        const response = await fetch('/api/themes');
        const data = await response.json();
        if (data.themes && data.themes.length > 0){
            const banner = document.getElementById('themes-banner');
            
            data.themes.forEach(theme => {
                const themeDiv = document.createElement('div');
                themeDiv.className='theme-item';
                themeDiv.innerHTML=`<strong>${theme.name}</strong>${theme.description ? ': ' + theme.description : ''}`;
                banner.appendChild(themeDiv);
            });
            banner.classList.add('active');
        }
    } catch (e) {
        console.error('Error loading themes: ', e);
    }
}
window.addEventListener("DOMContentLoaded", () => {
    const addProjectBtn = document.getElementById("add-project-btn");
    const addProjectForm = document.getElementById("add-project-form");
    const overlay = document.getElementById("overlay");
    const closeOverlay = document.getElementById("close-overlay");
    const hackProject = document.getElementById("hack-project");
    const hoursPreview = document.getElementById("project-hours");
    const screenshotInput = document.getElementById("screenshot-url");
    const screenshotPreview = document.getElementById("screenshot-preview");

    const detailsOverlay = document.getElementById("project-details-overlay");
    const closeDetails = document.getElementById("close-details");
    const submitOverlay = document.getElementById("submit-overlay");
    const closeSubmit = document.getElementById("close-submit");
    const submitForm = document.getElementById("submit-project-form");
    function resetAddForm(){
        addProjectForm.reset();
        hoursPreview.textContent="";
    }
    window.openSubmitForm = function(projectId){
        document.getElementById("submit-project-id").value = projectId;
        detailsOverlay.classList.add("hidden");
        submitOverlay.classList.remove("hidden");
    };
    async function showProjectDetails(projectId) {
        try {
            const response = await fetch (`/api/project-details/${projectId}`);
            const project = await response.json();

            if (!response.ok){
                alert('Error Loading Project Details');
                return;
            }
            const detailsHTML = `
            <h2>${project.name}</h2>
            <div class="details-grid">
                <div class="details-section">
                    <h3>Project Information</h3>
                    <p><strong>Description:</strong>${project.detail || 'No Description' }</p>
                    ${project.theme ? `<p><strong>Theme:</strong> <span class="theme-tag">${project.theme}</span></p> `: ''}
                    ${project.languages ? `<p><strong>Languages:</strong> ${project.languages}` : ''}
                </div>
                
                <div class="details-section">
                    <h3>Hours Tracking</h3>
                    <table class="hours-table">
                        <tr>
                            <td>Raw Hours(Hackatime):</td>
                            <td>${project.raw_hours} hrs <td>
                        </tr>
                        <tr>
                            <td>Approved Hours:</td>
                            <td>${project.approved_hours} hrs</td>
                        </tr>
                    </table>
                </div>
                ${project.summary ? `
                    <div class="details-section">
                        <h3>Project Summary</h3>
                        <p>${project.summary}</p>
                    </div>
                ` : ''}
                ${project.screenshot_url || project.github_url || project.demo_url ? `
                    <div class="details-section">
                        <h3>Links</h3>
                        ${project.screenshot_url ? `<p><a href="${project.screenshot_url}" target="_blank"> View Screenshot</a></p>` : '' }
                        ${project.github_url ? `<p><a href="${project.github_url}" target="_blank">Github Repository</a></p>` : ''}
                        ${project.demo_url ? `<p><a href="${project.demo_url}" target="_blank">Live Demo</a></p>`: ""}
                    </div>
                    `:''}
                ${project.comments && project.comments.length > 0 ? `
                    <div class="details-section">
                        <h3>Admin Comments</h3>
                        <div class="comment-list">
                            ${project.comments.map(comment=>`
                                    <div class="comment-item">
                                        <div class="comment-author">${comment.admin_name}</div>
                                        <div class="comment-date">${comment.created_at}</div>
                                        <div class="comment-text">${comment.comment}</div>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                        ` : ''}
                    </div>

                    ${project.status == 'draft' ? `
                        <button class="btn-primary" onclick="openSubmitForm(${projectId})">Submit for Review</button>
                        `: ''}
                `;

                document.getElementById("project-details-content").innerHTML = detailsHTML;
                detailsOverlay.classList.remove("hidden");
        } catch (e){
            alert("Error Loading project details");
            console.error(e)
        }  
    }
    async function fetchProjectHours(projectCard) {
        const hoursDisplay = projectCard.querySelector(".hours-display");
        let projectName = projectCard.getAttribute('data-hackatime-project')

        if (!projectName){
            if (hoursDisplay) hoursDisplay.textContent = "No project linked";
            return;
        }
        projectName = projectName.trim();
        hoursDisplay.textContent="Fetching...";

        try {
            const params= new URLSearchParams({'project_name': projectName});
            const response = await fetch('/api/project-hours?' + params.toString());
            const data = await response.json();

            if (response.ok){
                hoursDisplay.textContent = `${(data.hours ?? 0).toFixed(2)} hrs`;
            } else {
                hoursDisplay.textContent= 'Error';
            }
        } catch (e){
            hoursDisplay.textContent = 'Error';
            console.error(e);
        }
    }
    submitForm?.addEventListener("submit", async(e)=>{
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
                alert('Project Submitted Successsfully!')
                submitOverlay.classList.add("hidden");
                detailsOverlay.classList.add("hidden");
                location.reload();
            } else {
                const err = await response.json();
                alert('Error: ' + (err.error || 'Could not be submitted!'));
            }
        } catch (e){
            alert("Error submitting project!");
            console.error(e)
        }
    });
    addProjectForm?.addEventListener("submit", async(e)=>{
        e.preventDefault();
        const projectName = document.getElementById("project-name").value.trim();
        const projectDetail = document.getElementById("project-detail").value;
        const hackProjectValue = document.getElementById("hack-project").value;
        if (!projectName){
            alert("Project name cannot be empty");
            return;
        }
        try {
            const response = await fetch ('/api/add-project', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    name: projectName,
                    detail: projectDetail,
                    hack_project: hackProjectValue
                })
            });
            if (!response.ok){
                const err = await response.json();
                alert('Error Adding Project: '+ (err.error || 'Unknown Error'));
                return;
            }
            const newProject = await response.json();
            const projectsGrid = document.getElementById("projects-grid");
            const projectCard = document.createElement("div");
            projectCard.className = "project-card";
            projectCard.dataset.projectId=newProject.id;
            projectCard.setAttribute('data-hackatime-project', newProject.hackatimeProject || '')
            projectCard.innerHTML = `
            <div class="project-card-header">
                <h3>${newProject.name}</h3>
                <span class="status-badge status-draft">Draft</span>
            </div>
            <p class="project-description">${newProject.detail || 'No Description'}</p>
            <div class="project-card-footer">
                <span class="hours-display">Fetching hours...</span>
                <button class="view-details-btn">View Details</button>
            </div>
            `;
            projectsGrid.appendChild(projectCard);
            fetchProjectHours(projectCard);
            projectCard.addEventListener("click", ()=>{
                showProjectDetails(newProject. id);
            });
            overlay.classList.add("hidden");
            resetAddForm();
        } catch (e){
            alert('Error adding project.');
            console.error(e);
        }
    });
    screenshotInput?.addEventListener("input", ()=>{
        const url = screenshotInput.value;
        if (url) {
            screenshotPreview.innerHTML = `<img src="${url}" alt="Screenshot preview" onerror="this.style.display='none'">`;
        } else {
            screenshotPreview.innerHTML="";
        }
    });
    hackProject?.addEventListener("change", async()=>{
        const projectName=hackProject.value;
        if (!projectName) {
            hoursPreview.textContent = '';
            return;
        }
        hoursPreview.textContent="Fetching hours...";
        try {
            const params = new URLSearchParams({project_name: projectName});
            const response = await fetch('/api/project-hours?' + params.toString());
            const data = await response.json();
            if (response.ok) {
                hoursPreview.textContent = `Hours Spent: ${(data.hours ?? 0).toFixed(2)} hr(s)`;
            } else {
                hoursPreview.textContent = 'Error: ' + (data.error || 'Could not fetch hours');
            }
        } catch (e) {
            hoursPreview.textContent = "Error fetching hours";
            console.error(e);
        }
    });
    submitOverlay?.addEventListener("click", (e)=>{
        if (e.target==submitOverlay){
            submitOverlay.classList.add("hidden");
        }
    });
    closeSubmit?.addEventListener("click", ()=>{
        submitOverlay.classList.add("hidden");
    });
    detailsOverlay?.addEventListener("click", (e)=>{
        if (e.target==detailsOverlay){
            detailsOverlay.classList.add("hidden");
        }
    });
    closeDetails?.addEventListener("click", ()=>{
        detailsOverlay.classList.add("hidden");
    });
    overlay?.addEventListener("click", (e)=>{
        if (e.target==overlay){
            overlay.classList.add("hidden");
            resetAddForm();
        }
    });
    closeOverlay?.addEventListener("click", ()=>{
        overlay.classList.add("hidden");
        resetAddForm();
    });
    addProjectBtn?.addEventListener("click", ()=>{
        overlay.classList.remove("hidden");
    });
    const projectCards = document.querySelectorAll(".project-card");
    projectCards.forEach(card => {
        fetchProjectHours(card);
        card.addEventListener("click", ()=>{
            const projectId = card.dataset.projectId;
            showProjectDetails(projectId)
        });
    });
});
