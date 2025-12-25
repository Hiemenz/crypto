
import React from 'react';
import { Menu, X, LogOut } from 'lucide-react';

const DashboardLayout = ({
    children,
    sidebarContent,
    sidebarOpen,
    setSidebarOpen,
    onLogout
}) => {
    return (
        <div className="flex h-screen overflow-hidden bg-app text-primary font-sans">
            {/* Mobile Sidebar Overlay */}
            {sidebarOpen && (
                <div
                    className="fixed inset-0 bg-black/80 z-40 md:hidden backdrop-blur-sm transition-opacity"
                    onClick={() => setSidebarOpen(false)}
                />
            )}

            {/* Sidebar */}
            <aside className={`
                fixed inset-y-0 left-0 z-50 w-72 bg-panel border-r border-border-subtle flex flex-col transition-transform duration-300 ease-in-out
                md:relative md:translate-x-0
                ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
            `}>
                {/* Brand Header */}
                <div className="h-[72px] flex items-center justify-between px-6 border-b border-border-subtle bg-app/50 backdrop-blur-md">
                    <div className="flex items-center gap-2">
                        <span className="font-display font-bold text-lg tracking-tight pl-2">SignalStack</span>
                    </div>
                    <button onClick={() => setSidebarOpen(false)} className="md:hidden text-muted hover:text-white">
                        <X size={20} />
                    </button>
                </div>

                {/* Sidebar Content (Asset List) */}
                <div className="flex-1 overflow-hidden flex flex-col min-h-0">
                    {sidebarContent}
                </div>

                {/* User Footer */}
                <div className="p-4 border-t border-border-subtle bg-app/30">
                    <button
                        onClick={onLogout}
                        className="flex items-center gap-3 w-full px-4 py-3 text-sm font-medium text-muted hover:text-white hover:bg-hover rounded-lg transition-colors"
                    >
                        <LogOut size={16} />
                        <span>Sign Out</span>
                    </button>
                </div>
            </aside>

            {/* Main Content */}
            <main className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
                {/* Mobile Header */}
                <div className="md:hidden h-[60px] flex items-center justify-between px-4 border-b border-border-subtle bg-panel">
                    <button onClick={() => setSidebarOpen(true)} className="text-white">
                        <Menu size={24} />
                    </button>
                    <span className="font-bold text-lg">SignalStack</span>
                    <div className="w-6" /> {/* Spacer */}
                </div>

                {children}
            </main>
        </div>
    );
};

export default DashboardLayout;
