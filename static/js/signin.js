const signupform = document.getElementById("signup-form");
const verifyform = document.getElementById("verify-form");

signupform.addEventListener("submit", (e)=>{
    signupform.style.display = "none";
    verifyform.style.display = "block";

    const btn = signupform.querySelector("button[type='submit']");
    if (btn) btn.disabled=true;
});

verifyform.addEventListener("submit", (e) =>{
    const btn = verifyform.querySelector("button[type='submit']");
    if (btn) btn.disabled=true;
});