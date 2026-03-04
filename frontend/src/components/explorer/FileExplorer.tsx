import { useState, useEffect } from "react";
import { Folder, File, ArrowUpLeft, X } from "lucide-react";

interface FSItem {
  name: string;
  path: string;
  type: "dir" | "file";
  size: number;
}

export default function FileExplorer({ 
  onSelect, 
  onClose 
}: { 
  onSelect: (path: string) => void,
  onClose: () => void 
}) {
  const [currentPath, setCurrentPath] = useState("~");
  const [items, setItems] = useState<FSItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchDir = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const res = await fetch("http://127.0.0.1:7861/api/fs/list", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: currentPath }),
        });
        const data = await res.json();
        
        if (data.error) {
          setError(data.error);
        } else {
          setItems(data.items);
          setCurrentPath(data.current_path);
        }
      } catch (err: any) {
        setError(err.message);
      } finally {
        setIsLoading(false);
      }
    };
    
    fetchDir();
  }, [currentPath]);

  const formatSize = (bytes: number) => {
    if (bytes === 0) return "";
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  };

  return (
    <div className="absolute inset-0 bg-black/80 z-40 flex items-center justify-center backdrop-blur-sm p-8">
      <div className="w-full max-w-3xl h-full max-h-[600px] bg-zinc-950 border-2 border-[var(--accent)] rounded-xl flex flex-col shadow-[0_0_30px_var(--tint)] overflow-hidden font-mono">
        {/* Header */}
        <div className="bg-[var(--accent)] text-black px-4 py-2 flex items-center justify-between font-bold">
          <span>SYSTEM_EXPLORER</span>
          <button onClick={onClose} className="hover:bg-black hover:text-[var(--accent)] rounded p-1 transition-colors">
            <X size={18} />
          </button>
        </div>

        {/* Path Bar */}
        <div className="bg-zinc-900 px-4 py-3 border-b border-white/10 flex items-center gap-2">
          <span className="text-[var(--accent)] opacity-70">PATH:</span>
          <input 
            type="text" 
            value={currentPath}
            onChange={(e) => setCurrentPath(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && setCurrentPath(e.currentTarget.value)}
            className="flex-1 bg-transparent border-none outline-none text-white text-sm"
          />
        </div>

        {/* File List */}
        <div className="flex-1 overflow-y-auto crt-scroll p-2">
          {isLoading ? (
            <div className="flex items-center justify-center h-full text-[var(--accent)] animate-pulse">
              READING DIRECTORY...
            </div>
          ) : error ? (
            <div className="flex items-center justify-center h-full text-red-500">
              ERROR: {error}
            </div>
          ) : (
            <table className="w-full text-sm text-left text-zinc-300">
              <thead className="text-xs uppercase text-zinc-500 sticky top-0 bg-zinc-950 z-10 border-b border-white/10">
                <tr>
                  <th className="px-4 py-2">Name</th>
                  <th className="px-4 py-2 w-24 text-right">Size</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item, idx) => (
                  <tr 
                    key={idx}
                    onClick={() => {
                      if (item.type === "dir") setCurrentPath(item.path);
                      else onSelect(item.path);
                    }}
                    className="hover:bg-[var(--accent)]/10 cursor-pointer border-b border-white/5 transition-colors group"
                  >
                    <td className="px-4 py-2 flex items-center gap-3">
                      {item.name === ".." ? (
                        <ArrowUpLeft size={16} className="text-[var(--accent)]" />
                      ) : item.type === "dir" ? (
                        <Folder size={16} className="text-yellow-500" />
                      ) : (
                        <File size={16} className="text-blue-400" />
                      )}
                      <span className={`group-hover:text-[var(--accent)] truncate max-w-lg ${item.type === 'dir' ? 'font-bold text-white' : ''}`}>
                        {item.name}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right opacity-50 font-mono text-xs">
                      {formatSize(item.size)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
