export const signup = (email, password) => {
    try {
        const users = JSON.parse(localStorage.getItem('users') || '[]');

        // Check if user already exists
        if (users.find(u => u.email === email)) {
            return { success: false, message: 'User already exists' };
        }

        // Add new user
        const newUser = { email, password, createdAt: new Date().toISOString() };
        users.push(newUser);
        localStorage.setItem('users', JSON.stringify(users));

        return { success: true };
    } catch (error) {
        console.error('Signup error:', error);
        return { success: false, message: 'Failed to create account.' };
    }
};

export const login = (email, password) => {
    try {
        const users = JSON.parse(localStorage.getItem('users') || '[]');
        const user = users.find(u => u.email === email && u.password === password);

        if (user) {
            return { success: true, user };
        } else {
            return { success: false, message: 'Invalid credentials' };
        }
    } catch (error) {
        console.error('Login error:', error);
        return { success: false, message: 'Login failed.' };
    }
};
