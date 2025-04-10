// User management related functions
let currentUser = null;

// Register new user
async function register() {
    const username = document.getElementById('register-username').value;
    const password = document.getElementById('register-password').value;
    const email = document.getElementById('register-email').value;

    const formData = new FormData();
    formData.append('username', username);
    formData.append('password', password);
    formData.append('email', email);

    try {
        const response = await fetch('/api/register', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Registration failed');
        }

        const result = await response.json();
        alert('Registration successful! Please login.');
        showLoginForm();
    } catch (error) {
        alert(error.message);
    }
}

// Login step 1: Get verification code
async function login() {
    const username = document.getElementById('login-username').value;
    const password = document.getElementById('login-password').value;

    const formData = new FormData();
    formData.append('username', username);
    formData.append('password', password);

    try {
        const response = await fetch('/api/login', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Login failed');
        }

        const result = await response.json();
        alert('Verification code sent to your email!');
        document.getElementById('login-form').style.display = 'none';
        document.getElementById('mfa-form').style.display = 'block';
        document.getElementById('mfa-username').value = username;
    } catch (error) {
        alert(error.message);
    }
}

// Login step 2: Verify code and get token
async function verifyMFA() {
    const username = document.getElementById('mfa-username').value;
    const mfa_code = document.getElementById('mfa-code').value;

    const formData = new FormData();
    formData.append('username', username);
    formData.append('mfa_code', mfa_code);

    try {
        const response = await fetch('/api/login/mfa', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Verification failed');
        }

        const result = await response.json();
        localStorage.setItem('token', result.access_token);
        alert('Login successful!');
        await getCurrentUser();
        showUserDashboard();
    } catch (error) {
        alert(error.message);
    }
}

// Get current user info
async function getCurrentUser() {
    const token = localStorage.getItem('token');
    if (!token) return null;

    try {
        const response = await fetch('/api/users/me', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!response.ok) {
            if (response.status === 401) {
                localStorage.removeItem('token');
                showLoginForm();
                return null;
            }
            throw new Error('Failed to get user info');
        }

        currentUser = await response.json();
        return currentUser;
    } catch (error) {
        console.error(error);
        return null;
    }
}

// Get user list (admin only)
async function getUserList() {
    const token = localStorage.getItem('token');
    if (!token) return;

    try {
        const response = await fetch('/api/users', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!response.ok) {
            throw new Error('Failed to get user list');
        }

        const users = await response.json();
        const userList = document.getElementById('user-list');
        userList.innerHTML = '';

        users.forEach(user => {
            const userDiv = document.createElement('div');
            userDiv.className = 'user-item';
            userDiv.innerHTML = `
                <div>Username: ${user.username}</div>
                <div>Email: ${user.email}</div>
                <div>Role: ${user.role}</div>
                <div>Created: ${new Date(user.created_at).toLocaleString()}</div>
                ${currentUser.role === 'admin' ? `
                    <button onclick="editUser('${user.id}')">Edit</button>
                    <button onclick="deleteUser('${user.id}')">Delete</button>
                ` : ''}
            `;
            userList.appendChild(userDiv);
        });
    } catch (error) {
        console.error(error);
        alert(error.message);
    }
}

// Delete user
async function deleteUser(userId) {
    if (!confirm('Are you sure you want to delete this user?')) return;

    const token = localStorage.getItem('token');
    if (!token) return;

    try {
        const response = await fetch(`/api/users/${userId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!response.ok) {
            throw new Error('Failed to delete user');
        }

        alert('User deleted successfully');
        getUserList();
    } catch (error) {
        alert(error.message);
    }
}

// Edit user
async function editUser(userId) {
    const token = localStorage.getItem('token');
    if (!token) return;

    // Get current user data
    try {
        const response = await fetch(`/api/users/${userId}`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (!response.ok) {
            throw new Error('Failed to get user data');
        }

        const user = await response.json();
        document.getElementById('edit-user-id').value = userId;
        document.getElementById('edit-email').value = user.email;
        document.getElementById('edit-role').value = user.role;
        
        // Show edit form
        document.getElementById('edit-form').style.display = 'block';
    } catch (error) {
        alert(error.message);
    }
}

// Update user
async function updateUser() {
    const token = localStorage.getItem('token');
    if (!token) return;

    const userId = document.getElementById('edit-user-id').value;
    const email = document.getElementById('edit-email').value;
    const password = document.getElementById('edit-password').value;
    const role = document.getElementById('edit-role').value;

    const updateData = {
        email,
        role
    };
    if (password) {
        updateData.password = password;
    }

    try {
        const response = await fetch(`/api/users/${userId}`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(updateData)
        });

        if (!response.ok) {
            throw new Error('Failed to update user');
        }

        alert('User updated successfully');
        document.getElementById('edit-form').style.display = 'none';
        getUserList();
    } catch (error) {
        alert(error.message);
    }
}

// UI helper functions
function showLoginForm() {
    document.getElementById('register-form').style.display = 'none';
    document.getElementById('login-form').style.display = 'block';
    document.getElementById('mfa-form').style.display = 'none';
    document.getElementById('user-dashboard').style.display = 'none';
    document.getElementById('edit-form').style.display = 'none';
}

function showRegisterForm() {
    document.getElementById('register-form').style.display = 'block';
    document.getElementById('login-form').style.display = 'none';
    document.getElementById('mfa-form').style.display = 'none';
    document.getElementById('user-dashboard').style.display = 'none';
    document.getElementById('edit-form').style.display = 'none';
}

function showUserDashboard() {
    document.getElementById('register-form').style.display = 'none';
    document.getElementById('login-form').style.display = 'none';
    document.getElementById('mfa-form').style.display = 'none';
    document.getElementById('user-dashboard').style.display = 'block';
    document.getElementById('edit-form').style.display = 'none';
    getUserList();
}

// Check login status on page load
window.onload = async function() {
    const token = localStorage.getItem('token');
    if (token) {
        const user = await getCurrentUser();
        if (user) {
            showUserDashboard();
            return;
        }
    }
    showRegisterForm();  // 默认显示注册表单
};
