import { useState, useEffect } from 'react'
import Watchlist from './Watchlist'
import Outsiders from './Outsiders'
import { Bell, Search, Menu } from 'lucide-react'
import { dataUrl } from '../utils/storage'

function Dashboard() {
    const [data, setData] = useState(null)
    const [loading, setLoading] = useState(true)
    const [watchlist, setWatchlist] = useState(() => {
        try {
            const saved = localStorage.getItem('sereneWatchlist');
            return saved ? JSON.parse(saved) : ['BTC-USD', 'ETH-USD']; // Default defaults
        } catch {
            return ['BTC-USD'];
        }
    });

    // Persist watchlist
    useEffect(() => {
        localStorage.setItem('sereneWatchlist', JSON.stringify(watchlist));
    }, [watchlist]);

    useEffect(() => {
        fetch(dataUrl('latest_signals.json'))
            .then(res => res.json())
            .then(data => {
                setData(data)
                setLoading(false)
            })
            .catch(err => {
                console.error("Failed to fetch signals:", err)
                setLoading(false)
            })
    }, [])

    const addToWatchlist = (symbol) => {
        if (!watchlist.includes(symbol)) {
            if (watchlist.length >= 50) {
                alert("Watchlist limit reached (50). Please remove some assets.");
                return;
            }
            setWatchlist(prev => [...prev, symbol]);
        }
    }

    // Handle Search (simple prompt for now or modal later)
    const handleSearch = () => {
        // For MVP, just use browser find or implement a simple filter on the full list?
        // Let's implement a simple prompt add for now to satisfy "Search"
        const sym = prompt("Enter Symbol (e.g. SOL-USD):");
        if (sym) {
            const upper = sym.toUpperCase();
            // Verify it exists in our data
            if (data && data.signals.find(s => s.symbol === upper)) {
                addToWatchlist(upper);
            } else {
                alert("Symbol not found in latest signal data.");
            }
        }
    }

    return (
        <div className="min-h-screen pb-20">
            {/* Header */}
            <header className="sticky top-0 z-50 glass-card border-b-0 rounded-none border-b border-white/10 px-6 py-4">
                <div className="max-w-7xl mx-auto flex justify-between items-center">
                    <div className="flex items-center gap-3">
                        <div className="w-8 h-8 bg-gradient-to-tr from-blue-500 to-purple-500 rounded-lg flex items-center justify-center font-bold text-white">S</div>
                        <h1 className="text-xl font-bold text-white tracking-wide">Serene</h1>
                    </div>

                    <div className="flex items-center gap-4">
                        <button onClick={handleSearch} className="p-2 text-slate-400 hover:text-white transition-colors">
                            <Search className="w-5 h-5" />
                        </button>
                        <button className="p-2 text-slate-400 hover:text-white transition-colors relative">
                            <Bell className="w-5 h-5" />
                            {/* Notification dot if needed */}
                            <span className="absolute top-2 right-2 w-2 h-2 bg-red-500 rounded-full"></span>
                        </button>
                        {/* Mobile Menu Trigger - Optional */}
                    </div>
                </div>
            </header>

            <main className="max-w-7xl mx-auto px-6 py-8">
                {loading ? (
                    <div className="flex items-center justify-center py-20">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
                    </div>
                ) : !data ? (
                    <div className="text-center py-20 text-red-400">Failed to load signal data.</div>
                ) : (
                    <>
                        <div className="mb-8">
                            <h1 className="text-3xl font-bold text-white mb-2">Welcome back, Trader.</h1>
                            <p className="text-slate-400">
                                Markets are {data.signals.filter(s => s.side === 'buy').length > data.signals.filter(s => s.side === 'sell').length ? "bullish" : "mixed"} today.
                                You have <span className="text-white font-medium">{watchlist.length}</span> assets on watch.
                            </p>
                        </div>

                        <Watchlist
                            allSignals={data.signals}
                            watchlist={watchlist}
                            setWatchlist={setWatchlist}
                        />

                        <Outsiders
                            allSignals={data.signals}
                            watchlist={watchlist}
                            addToWatchlist={addToWatchlist}
                        />

                        {/* Footer / Info */}
                        <div className="text-center text-slate-600 text-sm mt-20">
                            <p>Data updated: {new Date(data.updated).toLocaleString()}</p>
                            <p>Serene Dashboard v1.0 • Built with ❤️</p>
                        </div>
                    </>
                )}
            </main>
        </div>
    )
}

export default Dashboard
