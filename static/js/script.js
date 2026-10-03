document.addEventListener("DOMContentLoaded", () => {

    const studentMenuToggle = document.getElementById('studentMenuToggle');
    const studentSidebar = document.getElementById('studentSidebar');
    if (studentMenuToggle && studentSidebar) {
        studentMenuToggle.addEventListener('click', () => {
            const isOpen = studentSidebar.classList.toggle('is-open');
            studentMenuToggle.setAttribute('aria-expanded', String(isOpen));
        });
        studentSidebar.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => {
            studentSidebar.classList.remove('is-open');
            studentMenuToggle.setAttribute('aria-expanded', 'false');
        }));
    }

    const studentProfileTrigger = document.getElementById('studentProfileTrigger');
    const studentProfilePanel = document.getElementById('studentProfilePanel');
    if (studentProfileTrigger && studentProfilePanel) {
        const closeStudentProfile = () => {
            studentProfilePanel.hidden = true;
            studentProfileTrigger.setAttribute('aria-expanded', 'false');
        };
        studentProfileTrigger.addEventListener('click', (event) => {
            event.stopPropagation();
            const isOpen = studentProfileTrigger.getAttribute('aria-expanded') === 'true';
            studentProfilePanel.hidden = isOpen;
            studentProfileTrigger.setAttribute('aria-expanded', String(!isOpen));
        });
        studentProfilePanel.addEventListener('click', (event) => event.stopPropagation());
        document.addEventListener('click', closeStudentProfile);
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') closeStudentProfile();
        });
    }

    document.querySelectorAll('[data-open-ai]').forEach((link) => {
        link.addEventListener('click', (event) => {
            event.preventDefault();
            document.getElementById('aiWidgetToggle')?.click();
        });
    });

    if (window.io) {
        const socket = window.io({ transports: ['websocket', 'polling'] });
        socket.on('complaint_updated', (payload) => {
            const card = document.querySelector(`[data-complaint-id="${payload.complaint_id}"]`);
            if (!card || !payload.status) return;
            const badge = card.querySelector('.badge');
            if (!badge) return;
            badge.className = `badge ${payload.status.toLowerCase().replace(/\s+/g, '-')}`;
            badge.textContent = payload.status;
        });
    }

    // 1. Auto-hide Flash/Alert Messages after 3 seconds
    const flashMessages = document.querySelectorAll('.alert');
    if (flashMessages.length > 0) {
        setTimeout(() => {
            flashMessages.forEach(msg => {
                msg.style.transition = "opacity 0.5s ease";
                msg.style.opacity = "0";
                setTimeout(() => msg.remove(), 500); // Remove from DOM after fade
            });
        }, 3000);
    }

    // 2. Registration Form Validation (Password Matching)
    const registerForm = document.getElementById('registerForm');
    const passwordInput = document.getElementById('password');
    const confirmPasswordInput = document.getElementById('confirm_password');

    if (registerForm && passwordInput && confirmPasswordInput) {
        const validatePasswords = () => {
            if (passwordInput.value !== confirmPasswordInput.value) {
                confirmPasswordInput.setCustomValidity("Passwords do not match!");
            } else {
                confirmPasswordInput.setCustomValidity("");
            }
        };
        passwordInput.addEventListener('change', validatePasswords);
        confirmPasswordInput.addEventListener('keyup', validatePasswords);
    }

    // 3. Status Update Confirmation for Admin/Staff
    const actionForms = document.querySelectorAll('.action-form');
    actionForms.forEach(form => {
        form.addEventListener('submit', (e) => {
            if (!confirm("Are you sure you want to update this complaint's status?")) {
                e.preventDefault();
            }
        });
    });

    const deleteAccountForms = document.querySelectorAll('.delete-account-form');
    deleteAccountForms.forEach(form => {
        form.addEventListener('submit', (event) => {
            if (!confirm('Delete this account? This action cannot be undone.')) {
                event.preventDefault();
            }
        });
    });

    // 4. File Upload Preview (Optional - for Student submitting images)
    const imageInput = document.getElementById('complaintImage');
    const imagePreview = document.getElementById('imagePreview');

    if (imageInput && imagePreview) {
        imageInput.addEventListener('change', function () {
            const file = this.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function (e) {
                    imagePreview.src = e.target.result;
                    imagePreview.style.display = 'block';
                }
                reader.readAsDataURL(file);
            } else {
                imagePreview.style.display = 'none';
            }
        });
    }

    const locationType = document.getElementById('locationType');
    const collegeCategory = document.getElementById('collegeCategory');
    const hostelCategory = document.getElementById('hostelCategory');
    if (locationType && collegeCategory && hostelCategory) {
        const updateCategories = () => {
            const isCollege = locationType.value === 'College';
            const activeCategory = isCollege ? collegeCategory : hostelCategory;
            const inactiveCategory = isCollege ? hostelCategory : collegeCategory;
            const hasLocation = Boolean(locationType.value);

            activeCategory.hidden = !hasLocation;
            activeCategory.disabled = !hasLocation;
            inactiveCategory.hidden = true;
            inactiveCategory.disabled = true;
            inactiveCategory.value = '';
        };

        locationType.addEventListener('change', updateCategories);
        updateCategories();
    }

    const managementMenuToggle = document.getElementById('managementMenuToggle');
    const managementMenuPanel = document.getElementById('managementMenuPanel');
    if (managementMenuToggle && managementMenuPanel) {
        managementMenuToggle.addEventListener('click', () => {
            const isOpen = managementMenuToggle.getAttribute('aria-expanded') === 'true';
            managementMenuToggle.setAttribute('aria-expanded', String(!isOpen));
            managementMenuPanel.hidden = isOpen;
            managementMenuToggle.classList.toggle('is-open', !isOpen);
        });
    }

    const sidebarLinks = document.querySelectorAll('[data-admin-panel]');
    const adminPanels = document.querySelectorAll('[data-admin-panel-content]');
    sidebarLinks.forEach(link => {
        link.addEventListener('click', () => {
            const selectedPanel = link.dataset.adminPanel;
            sidebarLinks.forEach(item => item.classList.toggle('is-active', item === link));
            adminPanels.forEach(panel => {
                const isSelected = panel.dataset.adminPanelContent === selectedPanel;
                panel.hidden = !isSelected;
                panel.classList.toggle('is-visible', isSelected);
            });
        });
    });

    const sidebarToggle = document.getElementById('sidebarToggle');
    const adminSidebar = document.getElementById('adminSidebar');
    if (sidebarToggle && adminSidebar) {
        sidebarToggle.addEventListener('click', () => {
            const isOpen = adminSidebar.classList.toggle('is-open');
            sidebarToggle.setAttribute('aria-expanded', String(isOpen));
        });
    }

    const notificationToggle = document.querySelector('.notification-toggle');
    const notificationPanel = document.querySelector('.notification-panel');
    if (notificationToggle && notificationPanel) {
        const closeNotifications = () => {
            notificationPanel.hidden = true;
            notificationToggle.setAttribute('aria-expanded', 'false');
        };

        notificationToggle.addEventListener('click', (event) => {
            event.stopPropagation();
            const isOpen = notificationToggle.getAttribute('aria-expanded') === 'true';
            notificationPanel.hidden = isOpen;
            notificationToggle.setAttribute('aria-expanded', String(!isOpen));
        });

        document.addEventListener('click', (event) => {
            if (!notificationPanel.contains(event.target) && event.target !== notificationToggle) {
                closeNotifications();
            }
        });

        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                closeNotifications();
            }
        });
    }

    const aiWidgetToggle = document.getElementById('aiWidgetToggle');
    const aiWidgetPanel = document.getElementById('aiWidgetPanel');
    const aiWidgetClose = document.getElementById('aiWidgetClose');
    if (aiWidgetToggle && aiWidgetPanel) {
        const closeAiWidget = () => {
            aiWidgetPanel.hidden = true;
            aiWidgetToggle.setAttribute('aria-expanded', 'false');
        };
        aiWidgetToggle.addEventListener('click', () => {
            const isOpen = aiWidgetToggle.getAttribute('aria-expanded') === 'true';
            aiWidgetPanel.hidden = isOpen;
            aiWidgetToggle.setAttribute('aria-expanded', String(!isOpen));
        });
        aiWidgetClose?.addEventListener('click', closeAiWidget);
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') closeAiWidget();
        });
    }

    const aiQueryForm = document.getElementById('aiQueryForm');
    const aiQueryResult = document.getElementById('aiQueryResult');
    if (aiQueryForm && aiQueryResult) {
        document.querySelectorAll('[data-ai-prompt]').forEach((button) => {
            button.addEventListener('click', () => {
                const question = document.getElementById('aiQuestion');
                if (question) {
                    question.value = button.dataset.aiPrompt;
                    question.focus();
                }
            });
        });
        aiQueryForm.addEventListener('submit', async (event) => {
            event.preventDefault();
            aiQueryResult.textContent = 'Analyzing complaint data...';
            try {
                const response = await fetch(aiQueryForm.dataset.endpoint || '/admin/ai-query', {
                    method: 'POST',
                    body: new FormData(aiQueryForm),
                    headers: { 'Accept': 'application/json' },
                });
                const result = await response.json();
                aiQueryResult.textContent = response.ok ? result.answer : (result.error || 'Unable to answer that question.');
            } catch (error) {
                aiQueryResult.textContent = 'AI query is temporarily unavailable.';
            }
        });
    }

    // Dynamic Search Filter for Complaints
    const setupSearchFilter = (inputId, listId) => {
        const searchInput = document.getElementById(inputId);
        const complaintList = document.getElementById(listId);

        if (searchInput && complaintList) {
            searchInput.addEventListener('input', function (e) {
                const term = e.target.value.toLowerCase();
                const cards = complaintList.querySelectorAll('.complaint-card');

                cards.forEach(card => {
                    const textContent = card.textContent.toLowerCase();
                    if (textContent.includes(term)) {
                        card.style.display = '';
                    } else {
                        card.style.display = 'none';
                    }
                });
            });
        }
    };

    setupSearchFilter('adminComplaintSearch', 'adminComplaintList');
    setupSearchFilter('staffComplaintSearch', 'staffComplaintList');
    setupSearchFilter('studentComplaintSearch', 'studentComplaintList');

    // AI Analysis Generation
    const aiButtons = document.querySelectorAll('.generate-ai-btn');
    aiButtons.forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const complaintId = btn.getAttribute('data-id');
            const csrf = btn.getAttribute('data-csrf');
            const container = btn.closest('.ai-analysis-section');
            const resultsDiv = container.querySelector('#ai-results-' + complaintId);
            const errorDiv = container.querySelector('.ai-error');

            btn.disabled = true;
            btn.textContent = 'Generating... (Please wait)';
            errorDiv.style.display = 'none';
            resultsDiv.style.display = 'none';

            try {
                const formData = new FormData();
                formData.append('csrf_token', csrf);

                const response = await fetch('/api/ai/analyze/' + complaintId, {
                    method: 'POST',
                    body: formData,
                    headers: { 'Accept': 'application/json' }
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.error || 'Failed to generate analysis.');
                }

                resultsDiv.querySelector('.ai-cat').textContent = data.category;
                resultsDiv.querySelector('.ai-pri').textContent = data.priority;
                resultsDiv.querySelector('.ai-dep').textContent = data.department;
                resultsDiv.querySelector('.ai-sum').textContent = data.summary;
                resultsDiv.querySelector('.ai-act').textContent = data.next_action;
                resultsDiv.querySelector('.ai-draft').textContent = data.draft_response;

                resultsDiv.style.display = 'block';
                btn.style.display = 'none'; // Hide button after success

            } catch (error) {
                errorDiv.textContent = error.message;
                errorDiv.style.display = 'block';
                btn.disabled = false;
                btn.textContent = 'Generate AI Analysis';
            }
        });
    });
});