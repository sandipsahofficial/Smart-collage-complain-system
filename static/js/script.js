document.addEventListener("DOMContentLoaded", () => {

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
    if (registerForm) {
        registerForm.addEventListener('submit', (e) => {
            const password = document.getElementById('password').value;
            const confirmPassword = document.getElementById('confirm_password').value;

            if (password !== confirmPassword) {
                e.preventDefault(); // Form submit roko
                alert("Passwords do not match! Please enter exactly same passwords.");
            }
        });
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
});