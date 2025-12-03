window.addEventListener("DOMContentLoaded", () => {
    const hackProject = document.getElementById("hack-project");
    const hoursDisplayOverlay = document.getElementById('project-hours');   
    const addProjectForm = document.getElementById("add-project-form");
    const addProjectIcon = document.getElementById("icon");
    const addProjectOverlay = document.getElementById("add-project");
    const closeOverlay = document.getElementById("close-overlay");
    const mainOverlay = document.getElementById("overlay"); 

    async function fetchProjectHours(projectBox){
        const projectNameElem = projectBox.querySelector(".open");
        const hoursDisplay = projectBox.querySelector(".hours-display");
        let projectName = projectBox.getAttribute('data-hackatime-project');
        if (!projectName || !hoursDisplay) {
            hoursDisplay.textContent = "No project selected.";
            return;
        };
        projectName = projectName.trim();
        hoursDisplay.textContent = "Fetching hours...";
        try {
            const params = new URLSearchParams({ 'project_name': projectName });
            const response = await fetch('/api/project-hours?' + params.toString());
            const data = await response.json();
            if (response.ok) {
                hoursDisplay.textContent = 'Hours Spent: ' + ((data.hours ?? 0).toFixed(2)) + ' hr(s)';
            } else {
                hoursDisplay.textContent = 'Error: ' + (data.error || 'Could not fetch hours');
            }
        } catch (e){
            hoursDisplay.textContent = 'Error fetching hours';
            console.error(e);
        }
    }
    const projectBoxes = document.querySelectorAll(".project-box");
    for (const box of projectBoxes){
        fetchProjectHours(box);
    }
    document.querySelectorAll('.review-status, .shipped-status').forEach(checkbox => {
        checkbox.addEventListener('click', (e) => e.preventDefault())
    });
    document.querySelectorAll('.open').forEach(openButton => {
        const projectBox = openButton.closest('.project-box');
        const hiddenDetails = projectBox ? projectBox.querySelector('.hidden') : null;
        if (!projectBox || !hiddenDetails) return;
        let isOpen = false;
        openButton.addEventListener('click', ()=> {
            if (!isOpen) {
                hiddenDetails.style.display = 'block';
                projectBox.style.height = '150px';
                fetchProjectHours(projectBox);
            } else {
                hiddenDetails.style.display = 'none';
                projectBox.style.height = '30px';
            }
            projectBox.style.transition = 'all 0.3s ease';
            isOpen = !isOpen;
        });
    });
    hackProject?.addEventListener("change", async()=>{
        const projectName = hackProject.value;
        if (!hoursDisplayOverlay) return;
        if (!projectName){
            hoursDisplayOverlay.textContent = "Please select a project.";
            return;
        }
        hoursDisplayOverlay.textContent = "Fetching hours...";
        try {
            const params = new URLSearchParams({ project_name: projectName });
            const response = await fetch('/api/project-hours?' + params.toString());
            const data = await response.json();
            hoursDisplayOverlay.textContent = response.ok
                ? 'Hours Spent: ' + ((data.hours ?? 0).toFixed(2)) + ' hr(s)'
                : 'Error: ' + (data.error || 'Could not fetch hours');
        } catch (e){
            hoursDisplayOverlay.textContent = 'Error fetching hours';
            console.error(e);
        }
    });
    function resetOverlay(){
        addProjectForm.reset();
        if (hackProject) hackProject.value = "";
        if (hoursDisplayOverlay) hoursDisplayOverlay.textContent = "No Project Selected";
    }
    function overlayClickClose(e){
        if (e.target === mainOverlay){
            addProjectOverlay.style.display = "none";
            mainOverlay.style.display = "none";
            mainOverlay.removeEventListener("click", overlayClickClose);
            resetOverlay();
        }
    }
    addProjectIcon?.addEventListener("click", ()=>{
        addProjectOverlay.style.display = "block";
        mainOverlay.style.display = "block";
        mainOverlay.addEventListener("click", overlayClickClose);
    });
    closeOverlay?.addEventListener("click", ()=>{
        addProjectOverlay.style.display = "none";
        mainOverlay.style.display = "none";
        mainOverlay.removeEventListener("click", overlayClickClose);
        resetOverlay();
    });
    addProjectForm?.addEventListener("submit", async(e)=>{
        e.preventDefault();
        const projectNameInput = document.getElementById("project-name");
        const project_name = projectNameInput.value.trim();
        const project_detail = document.getElementById("project-detail").value;
        const hackProjectValue = document.getElementById("hack-project").value;
        if (!project_name){
            alert("Project name cannot be empty.");
            return;
        }
        try {
            const response = await fetch('/api/add-project', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: project_name,
                    detail: project_detail,
                    hack_project: hackProjectValue
                })
            });
            if (!response.ok) {
                const err = await response.json();
                alert('Error adding project: ' + (err.error || 'Unknown error'));
                return;
            }
            const projectBox = document.createElement("div");
            projectBox.className = "project-box";
            projectBox.setAttribute('data-hackatime-project', hackProjectValue);
            projectBox.innerHTML = `
                <p class="open">${project_name}</p>
                <div class="hidden">
                    <p class="hours-display">Hours spent: 0 hr(s)</p>
                    <p id="detail"><span style="font-style: italic;">${project_detail || 'No Description'}</span></p>
                    <input type="checkbox" value="review" name="review"  class="review-status">
                    <label for="checkbox">In Review</label>
                    <input type="checkbox" value="shipped" class="last-part shipped-status"> 
                    <label for="checkbox">Shipped</label>
                </div>
            `;
            document.getElementById("line3").appendChild(projectBox);
            const openButton = projectBox.querySelector('.open');
            const hiddenDetails = projectBox.querySelector('.hidden');
            let isOpen = true;
            openButton.addEventListener('click', ()=> {
                if (!isOpen) {
                    hiddenDetails.style.display = 'block';
                    projectBox.style.height = '150px';
                    fetchProjectHours(projectBox);
                } else {
                    hiddenDetails.style.display = 'none';
                    projectBox.style.height = '30px';
                }
                projectBox.style.transition = 'all 0.3s ease';
                isOpen = !isOpen;
            });
            fetchProjectHours(projectBox);
            projectBox.querySelectorAll('.review-status, .shipped-status').forEach(checkbox => {
                checkbox.addEventListener('click', (e) => e.preventDefault())
            });
            addProjectOverlay.style.display = "none";
            mainOverlay.style.display = "none";
            mainOverlay.removeEventListener("click", overlayClickClose);
            resetOverlay();
        } catch (e){
            alert('Error adding project.');
            console.error(e);
        }
    });
});