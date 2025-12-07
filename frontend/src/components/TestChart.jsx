import React, { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Scatter } from 'recharts';

const TestChart = () => {
  const [data, setData] = useState(null);
  
  useEffect(() => {
    fetch('/data/history/BTC-USD.json')
      .then(res => res.json())
      .then(json => {
        console.log('Loaded data:', json.data.length, 'points');
        const processed = json.data.map(item => ({
          date: item.Date,
          price: parseFloat(item.Close)
        }));
        setData(processed);
      })
      .catch(err => console.error('Error:', err));
  }, []);
  
  if (!data) return <div className="text-white p-8">Loading...</div>;
  
  return (
    <div className="bg-[#0B0D10] text-white p-8">
      <h1 className="text-2xl mb-4">Test Chart - {data.length} points</h1>
      <div className="h-[400px] bg-[#13161B] p-4 rounded">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <XAxis dataKey="date" stroke="#5F6670" tick={{fontSize:10}} />
            <YAxis stroke="#5F6670" tick={{fontSize:10}} />
            <Tooltip contentStyle={{backgroundColor:'#13161B', border:'1px solid #1E2228'}} />
            <Line type="monotone" dataKey="price" stroke="#00E5FF" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default TestChart;
