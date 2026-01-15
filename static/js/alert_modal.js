class AlertModal {
    constructor() {
        this.createModal();
    }

    createModal() {
        const existing = document.getElementById('custom-alert-modal');
        if (existing) existing.remove();
        const modal = document.createElement('div');
        modal.id = 'custom-alert-modal';
        modal.className = 'custom-alert-modal hidden';
        modal.innerHTML = `
            <div class="custom-alert-content">
                <div class="alert-icon" id="alert-icon"></div>
                <h3 id="alert-title">Alert</h3>
                <p id="alert-message"></p>
                <div class="alert-buttons">
                    <button class="alert-btn alert-btn-primary" id="alert-confirm">OK</button>
                    <button class="alert-btn alert-btn-secondary hidden" id="alert-cancel">Cancel</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        if (!document.getElementById('custom-alert-styles')) {
            const style = document.createElement('style');
            style.id = 'custom-alert-styles';
            style.textContent = `
                @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@600;700&display=swap');

                .custom-alert-modal {
                    position: fixed;
                    inset: 0;
                    background-color: rgba(13, 27, 42, 0.75);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    z-index: 10000;
                    backdrop-filter: blur(8px);
                    animation: alertFadeIn 0.3s ease;
                }

                .custom-alert-modal.hidden {
                    display: none;
                }

                @keyframes alertFadeIn {
                    from { opacity: 0; }
                    to { opacity: 1; }
                }

                @keyframes alertSlideUp {
                    from {
                        opacity: 0;
                        transform: translateY(30px) scale(0.95);
                    }
                    to {
                        opacity: 1;
                        transform: translateY(0) scale(1);
                    }
                }

                .custom-alert-content {
                    background: white;
                    padding: 40px;
                    border-radius: 20px;
                    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.4);
                    max-width: 480px;
                    width: 90%;
                    text-align: center;
                    animation: alertSlideUp 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
                    border: 2px solid rgba(35, 87, 137, 0.1);
                }

                .alert-icon {
                    width: 70px;
                    height: 70px;
                    margin: 0 auto 25px;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 36px;
                    font-weight: bold;
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
                }

                .alert-icon.success {
                    background: linear-gradient(135deg, #81C784 0%, #4CAF50 100%);
                    color: white;
                }

                .alert-icon.error {
                    background: linear-gradient(135deg, #EF5350 0%, #D32F2F 100%);
                    color: white;
                }

                .alert-icon.warning {
                    background: linear-gradient(135deg, #FFD54F 0%, #FFC107 100%);
                    color: #E65100;
                }

                .alert-icon.info {
                    background: linear-gradient(135deg, #90CAF9 0%, #235789 100%);
                    color: white;
                }

                #alert-title {
                    margin: 0 0 15px 0;
                    font-size: 28px;
                    color: #2c3e50;
                    font-family: 'Space Grotesk', sans-serif;
                    font-weight: 700;
                }

                #alert-message {
                    margin: 0 0 30px 0;
                    font-size: 16px;
                    color: #666;
                    line-height: 1.6;
                    font-family: 'Inter', sans-serif;
                }

                .alert-buttons {
                    display: flex;
                    gap: 12px;
                    justify-content: center;
                }

                .alert-btn {
                    padding: 14px 32px;
                    border: none;
                    border-radius: 10px;
                    font-size: 16px;
                    font-weight: 600;
                    cursor: pointer;
                    transition: all 0.3s ease;
                    font-family: 'Space Grotesk', sans-serif;
                    flex: 1;
                    max-width: 200px;
                }

                .alert-btn-primary {
                    background: linear-gradient(135deg, #235789 0%, #1a4567 100%);
                    color: white;
                    box-shadow: 0 4px 12px rgba(35, 87, 137, 0.3);
                }

                .alert-btn-primary:hover {
                    background: linear-gradient(135deg, #1a4567 0%, #235789 100%);
                    transform: translateY(-2px);
                    box-shadow: 0 6px 20px rgba(35, 87, 137, 0.4);
                }

                .alert-btn-primary:active {
                    transform: translateY(0);
                }

                .alert-btn-secondary {
                    background: white;
                    color: #2c3e50;
                    border: 2px solid #ddd;
                }

                .alert-btn-secondary:hover {
                    border-color: #235789;
                    background: #f8f9fa;
                    color: #235789;
                    transform: translateY(-2px);
                }

                .alert-btn-secondary:active {
                    transform: translateY(0);
                }

                @media (max-width: 600px) {
                    .custom-alert-content {
                        padding: 30px 25px;
                        max-width: 95%;
                    }

                    #alert-title {
                        font-size: 24px;
                    }

                    #alert-message {
                        font-size: 15px;
                    }

                    .alert-icon {
                        width: 60px;
                        height: 60px;
                        font-size: 32px;
                    }

                    .alert-buttons {
                        flex-direction: column;
                    }

                    .alert-btn {
                        max-width: 100%;
                    }
                }
            `;
            document.head.appendChild(style);
        }
    }

    show(message, type = 'info', title = null) {
        return new Promise((resolve) => {
            const modal = document.getElementById('custom-alert-modal');
            const icon = document.getElementById('alert-icon');
            const titleEl = document.getElementById('alert-title');
            const messageEl = document.getElementById('alert-message');
            const confirmBtn = document.getElementById('alert-confirm');
            const cancelBtn = document.getElementById('alert-cancel');

            const icons = {
                success: '✓',
                error: '✕',
                warning: '!',
                info: 'i'
            };

            icon.textContent = icons[type] || icons.info;
            icon.className = `alert-icon ${type}`;

            const titles = {
                success: 'Success',
                error: 'Error',
                warning: 'Warning',
                info: 'Information'
            };
            titleEl.textContent = title || titles[type] || 'Alert';

            messageEl.textContent = message;

            cancelBtn.classList.add('hidden');

            modal.classList.remove('hidden');

            const handleConfirm = () => {
                modal.classList.add('hidden');
                confirmBtn.removeEventListener('click', handleConfirm);
                resolve(true);
            };

            confirmBtn.addEventListener('click', handleConfirm);
        });
    }

    confirm(message, title = 'Confirm Action') {
        return new Promise((resolve) => {
            const modal = document.getElementById('custom-alert-modal');
            const icon = document.getElementById('alert-icon');
            const titleEl = document.getElementById('alert-title');
            const messageEl = document.getElementById('alert-message');
            const confirmBtn = document.getElementById('alert-confirm');
            const cancelBtn = document.getElementById('alert-cancel');

            icon.textContent = '?';
            icon.className = 'alert-icon warning';

            titleEl.textContent = title;
            messageEl.textContent = message;
            cancelBtn.classList.remove('hidden');
            confirmBtn.textContent = 'Confirm';
            modal.classList.remove('hidden');
            const handleConfirm = () => {
                modal.classList.add('hidden');
                confirmBtn.removeEventListener('click', handleConfirm);
                cancelBtn.removeEventListener('click', handleCancel);
                confirmBtn.textContent = 'OK';
                resolve(true);
            };
            const handleCancel = () => {
                modal.classList.add('hidden');
                confirmBtn.removeEventListener('click', handleConfirm);
                cancelBtn.removeEventListener('click', handleCancel);
                confirmBtn.textContent = 'OK';
                resolve(false);
            };

            confirmBtn.addEventListener('click', handleConfirm);
            cancelBtn.addEventListener('click', handleCancel);
        });
    }

    prompt(message, title = 'Input Required', placeholder = '') {
        return new Promise((resolve) => {
            const modal = document.getElementById('custom-alert-modal');
            const icon = document.getElementById('alert-icon');
            const titleEl = document.getElementById('alert-title');
            const messageEl = document.getElementById('alert-message');
            const confirmBtn = document.getElementById('alert-confirm');
            const cancelBtn = document.getElementById('alert-cancel');

            icon.textContent = 'X';
            icon.className = 'alert-icon info';

            titleEl.textContent = title;
            messageEl.innerHTML = `
                <p style="margin-bottom: 15px;">${message}</p>
                <textarea 
                    id="alert-prompt-input" 
                    placeholder="${placeholder}"
                    rows="4"
                    style="width: 100%; padding: 12px; border: 2px solid #ddd; border-radius: 8px; 
                           font-size: 15px; font-family: 'Inter', sans-serif; resize: vertical;
                           transition: all 0.3s ease; min-height: 100px;"
                ></textarea>
            `;

            cancelBtn.classList.remove('hidden');
            confirmBtn.textContent = 'Submit';
            modal.classList.remove('hidden');

            const inputEl = document.getElementById('alert-prompt-input');
            setTimeout(() => inputEl.focus(), 100);

            inputEl.addEventListener('focus', () => {
                inputEl.style.borderColor = '#235789';
                inputEl.style.boxShadow = '0 0 0 3px rgba(35, 87, 137, 0.1)';
            });

            inputEl.addEventListener('blur', () => {
                inputEl.style.borderColor = '#ddd';
                inputEl.style.boxShadow = 'none';
            });
            
            const handleConfirm = () => {
                const value = inputEl.value.trim();
                if (!value) {
                    inputEl.style.borderColor = '#D32F2F';
                    inputEl.focus();
                    return;
                }
                modal.classList.add('hidden');
                confirmBtn.removeEventListener('click', handleConfirm);
                cancelBtn.removeEventListener('click', handleCancel);
                confirmBtn.textContent = 'OK';
                resolve(value);
            };
            
            const handleCancel = () => {
                modal.classList.add('hidden');
                confirmBtn.removeEventListener('click', handleConfirm);
                cancelBtn.removeEventListener('click', handleCancel);
                confirmBtn.textContent = 'OK';
                resolve(null);
            };

            inputEl.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && e.ctrlKey) {
                    handleConfirm();
                }
            });

            confirmBtn.addEventListener('click', handleConfirm);
            cancelBtn.addEventListener('click', handleCancel);
        });
    }
}

const alertModal = new AlertModal();

window.showAlert = (message, type = 'info', title = null) => {
    return alertModal.show(message, type, title);
};

window.showConfirm = (message, title = 'Confirm Action') => {
    return alertModal.confirm(message, title);
};

window.showPrompt = (message, title = 'Input Required', placeholder = '') => {
    return alertModal.prompt(message, title, placeholder);
};

window.alert = (message) => {
    return alertModal.show(message, 'info');
};

window.confirm = (message) => {
    return alertModal.confirm(message);
};

window.prompt = (message, defaultValue = '') => {
    return alertModal.prompt(message, 'Input Required', defaultValue);
};