import { useState, useEffect } from 'react'
import DailyReport from './components/DailyReport'
import './index.css'

function App() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  // Fetch index for now to ensure connectivity
  useEffect(() => {
    fetch('/data/index.json')
      .then(res => res.json())
      .then(data => {
        setData(data)
        setLoading(false)
      })
      .catch(err => {
        console.error("Failed to fetch data:", err)
        setLoading(false)
      })
  }, [])

  return (
    <div className="min-h-screen p-4">
      <header className="mb-8 text-center">
        <h1 className="text-3xl font-bold text-slate-800">Crypto Signal Station</h1>
        <p className="text-slate-500">React Migration Preview</p>
      </header>

      <main className="max-w-4xl mx-auto">
        {loading ? (
          <p>Loading...</p>
        ) : (
          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold mb-4">Available Reports</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {data && data.dates && data.dates.slice(0, 20).map(date => (
                <div key={date} className="p-2 bg-blue-50 text-blue-700 rounded text-center cursor-pointer hover:bg-blue-100">
                  {date}
                </div>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

export default App
