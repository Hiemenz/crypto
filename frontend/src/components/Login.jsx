import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import AuthLayout from './AuthLayout';
import { ArrowRight } from 'lucide-react';
import { login } from '../utils/auth';

const Login = ({ onLogin }) => {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');

    const handleLogin = (e) => {
        e.preventDefault();
        setError('');

        const result = login(email, password);
        if (result.success) {
            onLogin();
        } else {
            setError(result.message);
        }
    };

    return (
        <AuthLayout
            title="Welcome Back"
            subtitle="Sign in to continue"
        >
            <form onSubmit={handleLogin} className="space-y-5">
                {error && (
                    <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-xs p-3 rounded-lg">
                        {error}
                    </div>
                )}
                <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider ml-1">Email</label>
                    <input
                        type="email"
                        required
                        className="input-modern w-full text-sm font-medium"
                        placeholder="name@company.com"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                    />
                </div>

                <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider ml-1">Password</label>
                    <input
                        type="password"
                        required
                        className="input-modern w-full text-sm font-medium"
                        placeholder="••••••••"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                    />
                </div>

                <button
                    type="submit"
                    className="btn-primary w-full flex items-center justify-center gap-2 mt-2 group text-sm py-4"
                >
                    <span>Sign In</span>
                    <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
                </button>
            </form>

            <div className="mt-8 flex flex-col items-center gap-5">
                <div className="text-sm text-gray-500">
                    Don't have an account?{' '}
                    <Link to="/signup" className="text-white hover:text-gray-200 font-semibold transition-colors">
                        Sign up
                    </Link>
                </div>

                <button
                    onClick={onLogin}
                    className="btn-ghost text-xs py-2 px-4 uppercase tracking-wide"
                >
                    Skip authentication
                </button>
            </div>
        </AuthLayout>
    );
};

export default Login;
