
const reviewCheckbox = document.querySelectorAll('.review-status');
const shippedCheckbox = document.querySelectorAll('.shipped-status');

reviewCheckbox.forEach(checkbox =>{
    checkbox.addEventListener("click", (e) => e.preventDefault())
});

shippedCheckbox.forEach(checkbox => {
    checkbox.addEventListener("click", (e) => e.preventDefault())
});

const openButtons = document.querySelectorAll(".open");

openButtons.forEach(openButton =>{
    const projectBox = openButton.closest('.project-box');
    const hiddenDetails = projectBox ? projectBox.querySelector('.hidden') :  null;
    let isOpen = false;
    if (projectBox && hiddenDetails){
        openButton.addEventListener("click", ()=>{
            if (!isOpen) {
                setTimeout(()=>{
                    hiddenDetails.style.display="block";
                }, 200);
                projectBox.style.height = "150px";
                projectBox.style.transition = "all 0.3s ease";
                isOpen = true;
            } else {
                hiddenDetails.style.display = "none";
                projectBox.style.height = "60px";
                projectBox.style.transition = "all 0.3s ease";
                isOpen = false;
            }
        });
    }
});

const hackProject = document.getElementById('hack-project');
const hoursDisplay = document.getElementById('project-hours'); 
const addProjectForm = document.getElementById('add-project-form');


hackProject?.addEventListener("change", async()=>{
    const projectName = hackProject.value;
    if (!hoursDisplay) return;
    if (!projectName){
        hoursDisplay.textContent = "No Project Selected";
        return;
    }
    try{
        const params = new URLSearchParams({'project-name': projectName})
        const response = await fetch('/api/project-hours?'+params.toString());
        const data = await response.json();
        if (response.ok){
            hoursDisplay.textContent= 'Hours Spent: ' + (data.hours ?? 0);
        } else {
            hoursDisplay.textContent = 'Error: ' + (data.error || "Failed to fetch hours");
        }
    } catch(e){
        hoursDisplay.textContent = 'Failed to fetch hours!';
    }
});

const addProjectIcon = document.getElementById('icon');
const addProjectOverlay = document.getElementById('add-project');
const closeOverlay = document.getElementById('close-overlay');
const mainOverlay = document.getElementById('overlay');

addProjectIcon?.addEventListener("click", ()=>{
    addProjectOverlay.style.display = "block";
    mainOverlay.style.display = "block";
    mainOverlay.addEventListener('click', overlayClickClose)
});
closeOverlay?.addEventListener("click", ()=>{
    addProjectOverlay.style.display = "none";
    mainOverlay.style.display = "none";
    mainOverlay.removeEventListener('click', overlayClickClose)
});
function overlayClickClose(e){
    if (e.target == mainOverlay){
        addProjectOverlay.style.display = "none";
        mainOverlay.style.display = "none";
        mainOverlay.removeEventListener('click', overlayClickClose)
    }
}
addProjectForm.addEventListener("submit", async (e)=>{
    e.preventDefault();

    const projectName = document.getElementById('project-name').value;
    const projectDetail = document.getElementById('project-detail').value;
    const hackProjectValue = document.getElementById('hack-project').value;
    
    const response = await fetch("/api/add-project", {
        method: "POST",
        headers: {
            "Content-Type" : "application/json"
        },
        body: JSON.stringify({
            name: projectName,
            detail: projectDetail,
            hackProject: hackProjectValue
        })
    });
    const data = await response.json();
    if (response.ok){
        const projectBox = document.createElement("div");
        projectBox.classList.add("project-box");
        let hoursText = "Hours Spent: 0";
        projectBox.innerHTML = `
        <p class="open">${data.name}</p>
        <div class="hidden">
            <p class="hours-display">${hoursText}</p>
            <p><span style="font-style:italic;">${data.detail || 'No Description'}</span>
            <input type="checkbox" value="review" class="review-status">
            <label>In Review</label>
            <input type="checkbox" value="shipped" class="shipped status">
            <label>Shipped</label>
        `
    } else {
        alert("Failed to add Project: " + (data.error || "Unknown error"));
    }
});
