const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL ?? '';
const BUCKET = import.meta.env.VITE_SUPABASE_BUCKET ?? 'signalstack';

// Returns the public URL for a file in Supabase Storage.
// path examples: 'latest_signals.json', 'crosses.json', 'history/BTC-USD.json'
export const dataUrl = (path) =>
    `${SUPABASE_URL}/storage/v1/object/public/${BUCKET}/${path}`;
