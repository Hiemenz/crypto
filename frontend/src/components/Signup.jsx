import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import AuthLayout from './AuthLayout';
import { ArrowRight } from 'lucide-react';
import { signup } from '../utils/auth';

const Signup = ({ onLogin }) => {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');

    const handleSignup = (e) => {
        e.preventDefault();
        setError('');

        const result = signup(email, password);
        if (result.success) {
            onLogin();
        } else {
            setError(result.message);
        }
    };

    return (
        <AuthLayout
            title="Create Account"
            subtitle="Start your professional analysis journey"
        >
            <form onSubmit={handleSignup} className="space-y-5">
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
                        className="w-full bg-[#1A1A1A]/80 border border-white/5 rounded-lg px-4 py-3.5 text-white placeholder-gray-600 focus:outline-none focus:bg-[#202020] focus:ring-1 focus:ring-gray-500/50 transition-all font-medium text-sm"
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
                        className="w-full bg-[#1A1A1A]/80 border border-white/5 rounded-lg px-4 py-3.5 text-white placeholder-gray-600 focus:outline-none focus:bg-[#202020] focus:ring-1 focus:ring-gray-500/50 transition-all font-medium text-sm"
                        placeholder="••••••••"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                    />
                </div>

                <button
                    type="submit"
                    className="w-full bg-white text-black hover:bg-gray-100 font-bold text-sm py-4 rounded-lg transition-all duration-200 shadow-lg shadow-white/5 flex items-center justify-center gap-2 mt-2 group"
                >
                    <span>Create Account</span>
                    <ArrowRight size={16} className="group-hover:translate-x-0.5 transition-transform" />
                </button>
            </form>

            <div className="mt-8 flex flex-col items-center gap-5">
                <button
                    onClick={onLogin}
                    className="text-xs font-medium text-gray-500 hover:text-gray-300 transition-colors uppercase tracking-wide border-b border-transparent hover:border-gray-700 pb-0.5"
                >
                    Skip authentication
                </button>

                <div className="text-sm text-gray-500">
                    Already have an account?{' '}
                    <Link to="/login" className="text-white hover:text-gray-200 font-semibold transition-colors">
                        Log in
                    </Link>
                </div>
            </div>
        </AuthLayout>
    );
};

export default Signup;
