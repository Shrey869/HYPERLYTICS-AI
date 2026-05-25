import React, { useState, useEffect, useRef } from "react";
import { 
  Database, 
  Terminal, 
  LineChart as LineIcon, 
  Layers, 
  Trash2, 
  UploadCloud, 
  Play, 
  Cpu, 
  Sparkles, 
  Send, 
  Info, 
  CheckCircle, 
  AlertTriangle,
  RefreshCw,
  FolderOpen,
  Shield,
  Activity,
  LogOut,
  ArrowRight,
  ArrowLeft,
  Mic,
  Volume2,
  VolumeX,
  GripVertical,
  Maximize2,
  Save,
  SlidersHorizontal,
  LayoutDashboard,
  X
} from "lucide-react";
import { 
  ResponsiveContainer, 
  LineChart, 
  Line, 
  BarChart, 
  Bar, 
  AreaChart,
  Area,
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  Legend,
  PieChart,
  Pie,
  Cell
} from "recharts";

const API_URL = "http://localhost:8000";

interface Dataset {
  name: string;
  size_bytes: number;
  format: string;
}

interface UserProfile {
  id: string;
  email: string;
  name: string;
  picture?: string;
  role?: string;
}

interface Message {
  user_id?: string;
  role: "user" | "ai";
  content: string;
  sql?: string;
  chart?: {
    type: string;
    x: string;
    y: string;
    lineage?: string;
  } | null;
  data?: any[] | null;
  confidence_report?: any;
}

interface DashboardWidget {
  id: string;
  type: string;
  title: string;
  x: number;
  y: number;
  w: number;
  h: number;
  data_binding: {
    x_col: string;
    y_col: string | null;
    aggregation: string;
  };
}

interface DashboardConfig {
  id: string;
  dataset_name: string;
  title: string;
  widgets: DashboardWidget[];
  theme: string;
  filter_options: { [col: string]: any[] };
}

const DASHBOARD_COLORS = ["#4F46E5", "#0EA5E9", "#10B981", "#F97316", "#EF4444", "#8B5CF6", "#EC4899", "#14B8A6", "#F59E0B", "#6366F1"];

// Interactive visualizer resembling Power BI for chat data responses
function InteractiveChart({ data, defaultX, defaultY, defaultType }: {
  data: any[];
  defaultX?: string;
  defaultY?: string;
  defaultType?: string;
}) {
  const [chartType, setChartType] = useState<"bar" | "line" | "area" | "table">((defaultType as any) || "bar");
  
  const keys = data && data.length > 0 ? Object.keys(data[0]) : [];
  
  // Guess numeric keys for Y-axis
  const numericKeys = keys.filter(k => {
    return data.some(row => {
      const val = row[k];
      return typeof val === "number" || (!isNaN(Number(val)) && val !== null && val !== "");
    });
  });
  
  const [xAxisKey, setXAxisKey] = useState<string>(defaultX && keys.includes(defaultX) ? defaultX : (keys[0] || ""));
  const [yAxisKey, setYAxisKey] = useState<string>(
    defaultY && numericKeys.includes(defaultY) 
      ? defaultY 
      : (numericKeys[0] || (keys[1] ? keys[1] : keys[0]) || "")
  );

  // Synchronize when inputs change
  useEffect(() => {
    if (defaultX && keys.includes(defaultX)) setXAxisKey(defaultX);
    if (defaultY && numericKeys.includes(defaultY)) setYAxisKey(defaultY);
    if (defaultType && ["bar", "line", "area", "table"].includes(defaultType)) {
      setChartType(defaultType as any);
    }
  }, [defaultX, defaultY, defaultType, data]);

  if (!data || data.length === 0) return null;

  // Determine if the selected Y-axis column contains purely numeric values
  const isYNumeric = data.every(row => {
    const val = row[yAxisKey];
    return val === null || val === undefined || typeof val === "number" || (!isNaN(Number(val)) && val !== "");
  });

  let chartData = data;
  let finalYKey = yAxisKey;
  
  if (!isYNumeric && xAxisKey) {
    const counts: { [key: string]: number } = {};
    data.forEach(row => {
      const xVal = String(row[xAxisKey] ?? "N/A");
      counts[xVal] = (counts[xVal] || 0) + 1;
    });
    
    chartData = Object.keys(counts).map(key => ({
      [xAxisKey]: key,
      [`Count of ${yAxisKey}`]: counts[key]
    }));
    finalYKey = `Count of ${yAxisKey}`;
  }

  return (
    <div className="mt-4 p-4 rounded-xl bg-slate-50/60 border border-slate-200/80 w-full space-y-4 shadow-sm">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 pb-3 border-b border-slate-200/50">
        <div className="flex items-center gap-2">
          <span className="text-[9px] uppercase font-black text-slate-400 tracking-wider">Visual Deck</span>
          <div className="flex rounded-lg bg-slate-200/60 p-0.5 border border-slate-200">
            {(["bar", "line", "area", "table"] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setChartType(t)}
                className={`px-2 py-1 text-[9px] font-bold uppercase rounded-md transition-all border-0 cursor-pointer ${
                  chartType === t 
                    ? "bg-white text-primary shadow-sm" 
                    : "text-slate-500 hover:text-slate-900 bg-transparent"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        </div>
        
        {chartType !== "table" && (
          <div className="flex gap-2 text-[10px] w-full sm:w-auto">
            <div className="flex items-center gap-1">
              <span className="text-slate-400 font-bold">X:</span>
              <select 
                value={xAxisKey} 
                onChange={(e) => setXAxisKey(e.target.value)}
                className="bg-white border border-slate-200 text-[10px] font-semibold rounded px-1.5 py-0.5 text-slate-700 focus:outline-none cursor-pointer"
              >
                {keys.map(k => <option key={k} value={k}>{k}</option>)}
              </select>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-slate-400 font-bold">Y:</span>
              <select 
                value={yAxisKey} 
                onChange={(e) => setYAxisKey(e.target.value)}
                className="bg-white border border-slate-200 text-[10px] font-semibold rounded px-1.5 py-0.5 text-slate-700 focus:outline-none cursor-pointer"
              >
                {numericKeys.map(k => <option key={k} value={k}>{k}</option>)}
                {numericKeys.length === 0 && keys.map(k => <option key={k} value={k}>{k}</option>)}
              </select>
            </div>
          </div>
        )}
      </div>

      <div className="h-60 w-full flex items-center justify-center">
        {chartType === "table" ? (
          <div className="w-full h-full overflow-auto border border-slate-200 rounded-lg bg-white">
            <table className="w-full text-left border-collapse text-[10px]">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase tracking-wider sticky top-0">
                  {keys.map((k) => <th key={k} className="p-2 font-semibold">{k}</th>)}
                </tr>
              </thead>
              <tbody>
                {data.map((row, idx) => (
                  <tr key={idx} className="border-b border-slate-100 hover:bg-slate-50 text-slate-700">
                    {keys.map((k) => <td key={k} className="p-2 font-mono">{String(row[k])}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            {chartType === "bar" ? (
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.05)" />
                <XAxis dataKey={xAxisKey} stroke="#64748b" tick={{ fontSize: 9 }} />
                <YAxis stroke="#64748b" tick={{ fontSize: 9 }} />
                <Tooltip contentStyle={{ backgroundColor: "#ffffff", borderColor: "#e2e8f0", color: "#0f172a", fontSize: 10 }} />
                <Bar dataKey={finalYKey} fill="#4F46E5" radius={[4, 4, 0, 0]} name={finalYKey} />
              </BarChart>
            ) : chartType === "line" ? (
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.05)" />
                <XAxis dataKey={xAxisKey} stroke="#64748b" tick={{ fontSize: 9 }} />
                <YAxis stroke="#64748b" tick={{ fontSize: 9 }} />
                <Tooltip contentStyle={{ backgroundColor: "#ffffff", borderColor: "#e2e8f0", color: "#0f172a", fontSize: 10 }} />
                <Line type="monotone" dataKey={finalYKey} stroke="#0EA5E9" strokeWidth={2} dot={{ r: 3, fill: '#0EA5E9' }} name={finalYKey} />
              </LineChart>
            ) : (
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="colorArea" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10B981" stopOpacity={0.4}/>
                    <stop offset="95%" stopColor="#10B981" stopOpacity={0.0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.05)" />
                <XAxis dataKey={xAxisKey} stroke="#64748b" tick={{ fontSize: 9 }} />
                <YAxis stroke="#64748b" tick={{ fontSize: 9 }} />
                <Tooltip contentStyle={{ backgroundColor: "#ffffff", borderColor: "#e2e8f0", color: "#0f172a", fontSize: 10 }} />
                <Area type="monotone" dataKey={finalYKey} stroke="#10B981" strokeWidth={2} fillOpacity={1} fill="url(#colorArea)" name={finalYKey} />
              </AreaChart>
            )}
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

export default function App() {
  const [currentView, setCurrentView] = useState<"landing" | "login" | "register" | "dashboard">("landing");
  const [user, setUser] = useState<UserProfile | null>(null);
  const [googleClientId, setGoogleClientId] = useState<string>("");
  const [dashboardDefaultTab, setDashboardDefaultTab] = useState<"command" | "datasets" | "chat" | "forecasting">("command");
  const [activeModal, setActiveModal] = useState<"privacy" | "terms" | "api" | null>(null);
  
  // Sync view and restore auth config on load
  useEffect(() => {
    let activeUser: UserProfile | null = null;
    const storedUser = localStorage.getItem("userProfile");
    if (storedUser) {
      try {
        activeUser = JSON.parse(storedUser);
        setUser(activeUser);
      } catch (e) {
        console.error("Failed to parse userProfile:", e);
      }
    }
    
    // Fetch backend client ID configuration
    fetch(`${API_URL}/api/auth/config`)
      .then(res => res.json())
      .then(data => {
        if (data.google_client_id) {
          setGoogleClientId(data.google_client_id);
        }
      })
      .catch(err => console.error("Failed to fetch Google OAuth configuration:", err));

    const isLoggedIn = localStorage.getItem("isLoggedIn") === "true";
    if (isLoggedIn && activeUser) {
      setCurrentView("dashboard");
    } else {
      localStorage.removeItem("isLoggedIn");
      localStorage.removeItem("userProfile");
      setUser(null);
      setCurrentView("landing");
    }
  }, []);

  const navigateTo = (view: "landing" | "login" | "register" | "dashboard") => {
    if (view === "dashboard" && localStorage.getItem("isLoggedIn") !== "true") {
      setCurrentView("login");
    } else {
      setCurrentView(view);
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleLogout = () => {
    localStorage.removeItem("isLoggedIn");
    localStorage.removeItem("userProfile");
    setUser(null);
    navigateTo("landing");
  };

  const handleCredentialResponse = async (
    response: any,
    setLocalLoading: (l: boolean) => void,
    setLocalError: (e: string | null) => void
  ) => {
    setLocalLoading(true);
    setLocalError(null);
    try {
      const res = await fetch(`${API_URL}/api/auth/google`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id_token: response.credential })
      });
      if (res.ok) {
        const data = await res.json();
        localStorage.setItem("isLoggedIn", "true");
        localStorage.setItem("userProfile", JSON.stringify(data.user));
        setUser(data.user);
        navigateTo("dashboard");
      } else {
        const err = await res.json();
        setLocalError(err.detail || "Authentication verification failed.");
      }
    } catch (err) {
      setLocalError("Failed to connect to authentication server.");
    } finally {
      setLocalLoading(false);
    }
  };

  const handleSandboxLogin = async (
    userId: string,
    setLocalLoading: (l: boolean) => void,
    setLocalError: (e: string | null) => void
  ) => {
    setLocalLoading(true);
    setLocalError(null);
    try {
      const res = await fetch(`${API_URL}/api/auth/google`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id_token: userId })
      });
      if (res.ok) {
        const data = await res.json();
        localStorage.setItem("isLoggedIn", "true");
        localStorage.setItem("userProfile", JSON.stringify(data.user));
        setUser(data.user);
        navigateTo("dashboard");
      } else {
        const err = await res.json();
        setLocalError(err.detail || "Failed to log in to sandbox.");
      }
    } catch (err) {
      setLocalError("Authentication server offline.");
    } finally {
      setLocalLoading(false);
    }
  };

  // --- SUB-COMPONENT: LANDING VIEW ---
  const LandingView = () => {
    const [scrollY, setScrollY] = useState(0);
    const [hoverCardId, setHoverCardId] = useState<number | null>(null);
    const cardRefs = useRef<{ [key: number]: HTMLDivElement | null }>({});

    useEffect(() => {
      const handleScroll = () => setScrollY(window.scrollY);
      window.addEventListener("scroll", handleScroll, { passive: true });
      return () => window.removeEventListener("scroll", handleScroll);
    }, []);

    const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>, id: number, translateY: number) => {
      const card = cardRefs.current[id];
      if (!card) return;
      const rect = card.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const rotateX = ((rect.height / 2 - y) / (rect.height / 2)) * 10;
      const rotateY = ((x - rect.width / 2) / (rect.width / 2)) * 10;
      card.style.transform = `perspective(1000px) translateY(${translateY}px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale3d(1.02, 1.02, 1.02)`;
    };

    const handleMouseLeave = (id: number, translateY: number) => {
      const card = cardRefs.current[id];
      if (!card) return;
      card.style.transform = `perspective(1000px) translateY(${translateY}px) rotateX(0deg) rotateY(0deg) scale3d(1, 1, 1)`;
    };

    const FEATURES = [
      {
        id: 1,
        title: "SQL Agent Node",
        tagline: "Natural Language to DuckDB Engine",
        description: "Converts natural language questions directly to optimized, read-only SQL, running analytical operations in-memory under 15 milliseconds.",
        color: "#4F46E5",
        icon: Terminal
      },
      {
        id: 2,
        title: "Holt-Winters Forecaster",
        tagline: "Predictive Seasonality Analysis",
        description: "Computes exponential smoothing projections over time-series data with automated metrics analysis and custom confidence interval bands.",
        color: "#0EA5E9",
        icon: Activity
      },
      {
        id: 3,
        title: "Data Quality profiles",
        tagline: "Self-Cleaning Schema Contract",
        description: "Identifies null structures, maps column cardinalities, and profiles datasets instantly on drag-and-drop file ingestion.",
        color: "#10B981",
        icon: Layers
      },
      {
        id: 4,
        title: "Secure RLS Isolation",
        tagline: "Hashed Database Matrix Protocols",
        description: "Enforces strict row-level security boundaries and parameters, ensuring analytical execution sandboxing and file safety rules.",
        color: "#F97316",
        icon: Shield
      }
    ];

    return (
      <div className="min-h-screen bg-background grid-bg text-foreground flex flex-col justify-between relative">
        <div className="absolute top-0 left-0 w-full h-[600px] bg-gradient-to-b from-primary/5 to-transparent pointer-events-none"></div>
        <div className="absolute top-1/4 right-[-10%] w-[500px] h-[500px] rounded-full bg-secondary/5 blur-[120px] pointer-events-none"></div>

        {/* Aligned Landing Header */}
        <header className="fixed top-0 left-0 w-full h-20 border-b border-slate-200 bg-white/75 backdrop-blur-md z-50 px-6 md:px-12 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded bg-primary/10 border border-primary/20 animate-pulse-glow">
              <Cpu className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h1 className="text-sm font-black tracking-wider text-slate-800">HYPERLYTICS AI</h1>
              <span className="text-[9px] text-slate-400 uppercase tracking-widest block font-bold">AI-Powered Analytics OS</span>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <button onClick={() => navigateTo("login")} className="text-xs font-bold text-slate-500 hover:text-primary transition-colors cursor-pointer">
              Login
            </button>
            <button onClick={() => navigateTo("register")} className="btn-cyber px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider">
              Sign Up
            </button>
            <button onClick={() => navigateTo("dashboard")} className="btn-cyber px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider flex items-center gap-1.5">
              Launch App
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </header>

        {/* Hero */}
        <section className="pt-44 pb-20 px-6 md:px-12 text-center max-w-4xl mx-auto flex flex-col items-center justify-center flex-grow">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 border border-primary/20 text-primary text-[10px] uppercase font-black tracking-widest mb-6">
            <Sparkles className="w-3.5 h-3.5 text-secondary animate-spin" />
            Vite React SPA Edition
          </div>
          <h2 className="text-4xl md:text-6xl font-black tracking-tight text-slate-900 mb-6 leading-none">
            Ask your data anything.<br />
            <span className="bg-gradient-to-r from-primary to-secondary bg-clip-text text-transparent">
              Understand everything.
            </span>
          </h2>
          <p className="text-sm md:text-base text-slate-500 max-w-2xl leading-relaxed mb-10">
            Hyperlytics AI connects directly to DuckDB analytical kernels using the Model Context Protocol. Ingest, profile, and forecast large datasets instantly.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
            <button onClick={() => navigateTo("register")} className="btn-cyber px-8 py-3.5 rounded-xl text-xs font-bold uppercase tracking-widest flex items-center gap-2">
              Provision Account via Google
              <ArrowRight className="w-4 h-4" />
            </button>
            <button onClick={() => navigateTo("login")} className="btn-cyber px-8 py-3.5 rounded-xl text-xs font-bold uppercase tracking-widest">
              Connect Google Node
            </button>
          </div>
        </section>

        {/* 3D Cards Scroll Showcase */}
        <section className="py-20 px-6 md:px-12 max-w-7xl mx-auto space-y-12 w-full">
          <div className="text-center max-w-xl mx-auto space-y-2">
            <h3 className="text-xl font-black text-slate-800 uppercase tracking-wider">Holographic Deck Nodes</h3>
            <p className="text-xs text-slate-400">
              Scroll page or hover on cards to inspect their analytical functions.
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 pt-6">
            {FEATURES.map((feature, idx) => {
              const IconComponent = feature.icon;
              const scrollFactor = Math.min(Math.max((scrollY - 150) / 400, 0), 1);
              const translateY = (1 - scrollFactor) * (40 + idx * 20);
              const opacity = scrollFactor;
              return (
                <div 
                  key={feature.id}
                  ref={(el) => { cardRefs.current[feature.id] = el; }}
                  onMouseMove={(e) => handleMouseMove(e, feature.id, translateY)}
                  onMouseLeave={() => handleMouseLeave(feature.id, translateY)}
                  onMouseEnter={() => setHoverCardId(feature.id)}
                  onClick={() => {
                    const tabMap: { [key: number]: "command" | "datasets" | "chat" | "forecasting" } = {
                      1: "chat",
                      2: "forecasting",
                      3: "datasets",
                      4: "command"
                    };
                    const selectedTab = tabMap[feature.id] || "command";
                    setDashboardDefaultTab(selectedTab);
                    navigateTo("dashboard");
                  }}
                  style={{ 
                    transformStyle: "preserve-3d",
                    transition: "transform 0.15s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.5s ease-out",
                    opacity: opacity,
                    transform: `perspective(1000px) translateY(${translateY}px) rotateX(0deg) rotateY(0deg)`
                  }}
                  className="cyber-card p-6 rounded-2xl cursor-pointer flex flex-col justify-between min-h-[290px] relative overflow-hidden bg-white/70 border border-slate-200/50"
                >
                  <div 
                    className="absolute top-0 right-0 w-24 h-24 rounded-full blur-[40px] pointer-events-none transition-opacity duration-300"
                    style={{ 
                      backgroundColor: feature.color, 
                      opacity: hoverCardId === feature.id ? 0.22 : 0.04
                    }}
                  ></div>
                  <div className="space-y-4" style={{ transform: "translateZ(25px)" }}>
                    <div className="p-3 w-fit rounded-xl border transition-all" style={{ backgroundColor: `${feature.color}08`, borderColor: hoverCardId === feature.id ? feature.color : `${feature.color}15` }}>
                      <IconComponent className="w-5 h-5" style={{ color: feature.color }} />
                    </div>
                    <div>
                      <span className="text-[8px] font-bold uppercase tracking-widest text-slate-400 block mb-1">{feature.tagline}</span>
                      <h4 className="text-sm font-bold text-slate-800 tracking-wide">{feature.title}</h4>
                    </div>
                    <p className="text-xs text-slate-500 leading-relaxed">{feature.description}</p>
                  </div>
                  <div className="flex items-center gap-1.5 text-xs font-semibold mt-4 transition-colors" style={{ color: feature.color }}>
                    Inspect specifications
                    <ArrowRight className="w-3.5 h-3.5" />
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* Aligned Landing Footer */}
        <footer className="py-10 border-t border-slate-200 bg-white/50 text-center text-xs text-slate-400 w-full mt-auto">
          <div className="max-w-7xl mx-auto px-6 flex flex-col sm:flex-row justify-between items-center gap-4">
            <p>© 2026 HYPERLYTICS AI. Open Source Analytics Node.</p>
            <div className="flex gap-6 text-[10px] font-bold text-slate-400">
              <span onClick={() => setActiveModal("privacy")} className="hover:text-primary cursor-pointer transition-colors">Privacy protocol</span>
              <span onClick={() => setActiveModal("terms")} className="hover:text-primary cursor-pointer transition-colors">Workspace terms</span>
              <span onClick={() => setActiveModal("api")} className="hover:text-primary cursor-pointer transition-colors">API Specs</span>
            </div>
          </div>
        </footer>
      </div>
    );
  };

  // --- SUB-COMPONENT: LOGIN VIEW ---
  const LoginView = () => {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [customEmail, setCustomEmail] = useState("");

    useEffect(() => {
      if (googleClientId && (window as any).google) {
        try {
          (window as any).google.accounts.id.initialize({
            client_id: googleClientId,
            callback: (res: any) => handleCredentialResponse(res, setLoading, setError)
          });
          (window as any).google.accounts.id.renderButton(
            document.getElementById("google-login-btn"),
            { theme: "outline", size: "large", width: 380 }
          );
        } catch (e) {
          console.error("Failed to initialize Google login button:", e);
        }
      }
    }, [googleClientId]);

    const triggerWorkspaceAuth = () => {
      if (!customEmail || !customEmail.includes("@")) {
        setError("Please enter a valid company or personal workspace email address.");
        return;
      }
      handleSandboxLogin(`workspace_auth:${customEmail}`, setLoading, setError);
    };

    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-background grid-bg text-foreground relative px-4 py-12">
        <div className="absolute top-1/4 left-1/4 w-72 h-72 rounded-full bg-primary/5 blur-[100px] pointer-events-none"></div>
        
        <div className="max-w-md w-full relative z-10 flex flex-col gap-4">
          <button 
            onClick={() => navigateTo("landing")}
            className="w-fit flex items-center gap-2 px-3.5 py-2 rounded-xl border border-slate-200 bg-white/90 hover:bg-white text-xs font-bold text-slate-600 hover:text-primary transition-all cursor-pointer shadow-sm z-20"
          >
            <ArrowLeft className="w-4 h-4 text-primary" /> Back to Home
          </button>

          <div className="cyber-card w-full p-8 rounded-2xl border border-slate-200 bg-white/80 shadow-md">
            <div className="flex flex-col items-center text-center mb-8 mt-2">
              <div className="p-3 rounded-xl bg-primary/10 border border-primary/20 mb-3 animate-pulse-glow">
                <Cpu className="w-6 h-6 text-primary" />
              </div>
              <h2 className="text-xl font-black tracking-wider text-slate-800">ACCESS WAREHOUSE</h2>
              <p className="text-[10px] text-slate-400 uppercase tracking-widest mt-1 font-bold">Secure Single Sign-On</p>
            </div>

            {error && (
              <div className="mb-6 p-3.5 bg-red-50 border border-red-200 rounded-xl text-xs text-red-600 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-red-500 shrink-0" />
                {error}
              </div>
            )}

            <div className="space-y-6">
              {googleClientId && (
                <div className="space-y-4">
                  <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400 block mb-1">Google Workspace Auth</span>
                  <p className="text-xs text-slate-500 leading-relaxed m-0">
                    Authenticate directly using your corporate Google or Workspace account credentials.
                  </p>
                  <div className="w-full flex justify-center py-1">
                    {loading ? (
                      <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 py-3">
                        <svg className="animate-spin h-4 w-4 text-primary" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        Verifying credentials...
                      </div>
                    ) : (
                      <div id="google-login-btn" className="w-full min-h-[40px] flex justify-center"></div>
                    )}
                  </div>
                  
                  <div className="relative flex py-2 items-center">
                    <div className="flex-grow border-t border-slate-200"></div>
                    <span className="flex-shrink mx-4 text-[9px] text-slate-400 font-bold uppercase tracking-wider">or</span>
                    <div className="flex-grow border-t border-slate-200"></div>
                  </div>
                </div>
              )}

              <div className="space-y-4">
                <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400 block mb-1">Workspace Domain Auth</span>
                <p className="text-xs text-slate-500 leading-relaxed m-0">
                  Securely authorize using your company or standard workspace email address.
                </p>
                <div className="flex flex-col gap-2">
                  <input 
                    type="email" 
                    placeholder="you@company.com" 
                    value={customEmail}
                    onChange={(e) => setCustomEmail(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && triggerWorkspaceAuth()}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2.5 text-xs text-slate-800 focus:outline-none focus:border-primary transition-all"
                  />
                  <button 
                    onClick={triggerWorkspaceAuth}
                    disabled={loading || !customEmail}
                    className="w-full btn-cyber py-2.5 rounded-lg text-xs font-bold uppercase tracking-wider cursor-pointer"
                  >
                    Authorize Workspace Session
                  </button>
                </div>
              </div>
            </div>

            <div className="mt-8 pt-6 border-t border-slate-200 text-center text-xs text-slate-400">
              First time here?{" "}
              <button onClick={() => navigateTo("register")} className="text-primary hover:underline font-bold transition-colors cursor-pointer bg-transparent border-0">
                Register Workspace Node
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  };

  // --- SUB-COMPONENT: REGISTER VIEW ---
  const RegisterView = () => {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [customEmail, setCustomEmail] = useState("");

    useEffect(() => {
      if (googleClientId && (window as any).google) {
        try {
          (window as any).google.accounts.id.initialize({
            client_id: googleClientId,
            callback: (res: any) => handleCredentialResponse(res, setLoading, setError)
          });
          (window as any).google.accounts.id.renderButton(
            document.getElementById("google-register-btn"),
            { theme: "outline", size: "large", width: 380 }
          );
        } catch (e) {
          console.error("Failed to initialize Google register button:", e);
        }
      }
    }, [googleClientId]);

    const triggerWorkspaceAuth = () => {
      if (!customEmail || !customEmail.includes("@")) {
        setError("Please enter a valid company or personal workspace email address.");
        return;
      }
      handleSandboxLogin(`workspace_auth:${customEmail}`, setLoading, setError);
    };

    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-background grid-bg text-foreground relative px-4 py-12">
        <div className="absolute top-1/4 left-1/4 w-72 h-72 rounded-full bg-primary/5 blur-[100px] pointer-events-none"></div>
        
        <div className="max-w-md w-full relative z-10 flex flex-col gap-4">
          <button 
            onClick={() => navigateTo("landing")}
            className="w-fit flex items-center gap-2 px-3.5 py-2 rounded-xl border border-slate-200 bg-white/90 hover:bg-white text-xs font-bold text-slate-600 hover:text-primary transition-all cursor-pointer shadow-sm z-20"
          >
            <ArrowLeft className="w-4 h-4 text-primary" /> Back to Home
          </button>

          <div className="cyber-card w-full p-8 rounded-2xl relative border border-slate-200 bg-white/80 shadow-md">
            <div className="flex flex-col items-center text-center mb-8 mt-2">
              <div className="p-3 rounded-xl bg-primary/10 border border-primary/20 mb-3 animate-pulse-glow">
                <Cpu className="w-6 h-6 text-primary" />
              </div>
              <h2 className="text-xl font-black tracking-wider text-slate-800">PROVISION NODE</h2>
              <p className="text-[10px] text-slate-400 uppercase tracking-widest mt-1 font-bold">Configure Access Matrix</p>
            </div>

            {error && (
              <div className="mb-6 p-3.5 bg-red-50 border border-red-200 rounded-xl text-xs text-red-600 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-red-500 shrink-0" />
                {error}
              </div>
            )}

            <div className="space-y-6">
              {googleClientId && (
                <div className="space-y-4">
                  <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400 block mb-1">Google Workspace Provisioning</span>
                  <p className="text-xs text-slate-500 leading-relaxed m-0">
                    Create your profile using a corporate Google workspace identity node.
                  </p>
                  <div className="w-full flex justify-center py-1">
                    {loading ? (
                      <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 py-3">
                        <svg className="animate-spin h-4 w-4 text-primary" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        Provisioning account...
                      </div>
                    ) : (
                      <div id="google-register-btn" className="w-full min-h-[40px] flex justify-center"></div>
                    )}
                  </div>
                  
                  <div className="relative flex py-2 items-center">
                    <div className="flex-grow border-t border-slate-200"></div>
                    <span className="flex-shrink mx-4 text-[9px] text-slate-400 font-bold uppercase tracking-wider">or</span>
                    <div className="flex-grow border-t border-slate-200"></div>
                  </div>
                </div>
              )}

              <div className="space-y-4">
                <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400 block mb-1">Direct Domain SSO Provisioning</span>
                <p className="text-xs text-slate-500 leading-relaxed m-0">
                  Input your workspace email to provision a secure isolated space.
                </p>
                <div className="flex flex-col gap-2">
                  <input 
                    type="email" 
                    placeholder="you@company.com" 
                    value={customEmail}
                    onChange={(e) => setCustomEmail(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && triggerWorkspaceAuth()}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2.5 text-xs text-slate-800 focus:outline-none focus:border-primary transition-all"
                  />
                  <button 
                    onClick={triggerWorkspaceAuth}
                    disabled={loading || !customEmail}
                    className="w-full btn-cyber py-2.5 rounded-lg text-xs font-bold uppercase tracking-wider cursor-pointer"
                  >
                    Register Workspace Session
                  </button>
                </div>
              </div>
            </div>

            <div className="mt-8 pt-6 border-t border-slate-200 text-center text-xs text-slate-400">
              Already registered?{" "}
              <button onClick={() => navigateTo("login")} className="text-primary hover:underline font-bold transition-colors cursor-pointer bg-transparent border-0">
                Connect Existing Node
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  };

  // --- SUB-COMPONENT: DASHBOARD VIEW ---
  const DashboardView = () => {
    const [activeTab, setActiveTab] = useState<"command" | "datasets" | "chat" | "forecasting" | "audit">(dashboardDefaultTab as any);

    useEffect(() => {
      setActiveTab(dashboardDefaultTab as any);
    }, [dashboardDefaultTab]);
    const [datasets, setDatasets] = useState<Dataset[]>([]);
    const [selectedDataset, setSelectedDataset] = useState<string>("");
    const [schemaData, setSchemaData] = useState<any>(null);
    const [loading, setLoading] = useState<boolean>(false);
    const [error, setError] = useState<string | null>(null);
    const [successMsg, setSuccessMsg] = useState<string | null>(null);

    // Advanced forecasting states
    const [forecastingModel, setForecastingModel] = useState<string>("auto");
    const [seasonalityMode, setSeasonalityMode] = useState<string>("add");
    const [cleanOutliers, setCleanOutliers] = useState<boolean>(false);
    const [fillMethod, setFillMethod] = useState<string>("interpolate");
    const [confidenceLevel, setConfidenceLevel] = useState<number>(0.95);
    
    // Voice interface states and speech synthesis tools
    const [isListening, setIsListening] = useState<boolean>(false);
    const [isMuted, setIsMuted] = useState<boolean>(true);
    const recognitionRef = useRef<any>(null);

    // Confidence and alias corrections states
    const [correctionModalOpen, setCorrectionModalOpen] = useState<boolean>(false);
    const [correctionReport, setCorrectionReport] = useState<any>(null);
    const [correctingDataset, setCorrectingDataset] = useState<string>("");
    const [lastQueryText, setLastQueryText] = useState<string>("");
    const [aliasCorrections, setAliasCorrections] = useState<{ [token: string]: string }>({});

    // Resume-Grade Features States
    const [datasetFingerprint, setDatasetFingerprint] = useState<any>(null);
    const [offlineQueue, setOfflineQueue] = useState<any[]>([]);
    const [isOnline, setIsOnline] = useState<boolean>(navigator.onLine);
    const [activeCollaborators] = useState<any[]>([
      { name: "Sarah Connor", picture: "https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=150&h=150&q=80", color: "#4F46E5" },
      { name: "Alex Mercer", picture: "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=150&h=150&q=80", color: "#0EA5E9" }
    ]);
    const [queryLock, setQueryLock] = useState<string | null>(null);
    const [wsConnection, setWsConnection] = useState<WebSocket | null>(null);
    const [auditLogs, setAuditLogs] = useState<any[]>([]);
    const [driftWarning, setDriftWarning] = useState<any>(null);
    const [storyNarratives, setStoryNarratives] = useState<{ [msgIdx: number]: any }>({});
    const [narrativeLoading, setNarrativeLoading] = useState<number | null>(null);

    // Dashboard grid states
    const [dashboardConfig, setDashboardConfig] = useState<DashboardConfig | null>(null);
    const [dashboardLoading, setDashboardLoading] = useState<boolean>(false);
    const [widgetsData, setWidgetsData] = useState<{ [id: string]: any[] }>({});
    const [widgetsLoading, setWidgetsLoading] = useState<{ [id: string]: boolean }>({});
    const [globalFilters, setGlobalFilters] = useState<{ [col: string]: string[] }>({});
    const [crossFilters, setCrossFilters] = useState<{ [col: string]: string[] }>({});
    const [localWidgets, setLocalWidgets] = useState<DashboardWidget[]>([]);
    const [savingLayout, setSavingLayout] = useState<boolean>(false);
    const [showMetadata, setShowMetadata] = useState<boolean>(false);
    const [activeDragId, setActiveDragId] = useState<string | null>(null);
    const dragStartRef = useRef<{ mx: number; my: number; ox: number; oy: number } | null>(null);
    const [activeResizeId, setActiveResizeId] = useState<string | null>(null);
    const resizeStartRef = useRef<{ mx: number; my: number; ow: number; oh: number } | null>(null);
    const gridContainerRef = useRef<HTMLDivElement>(null);

    // Online/Offline status listeners
    useEffect(() => {
      const handleOnline = () => setIsOnline(true);
      const handleOffline = () => setIsOnline(false);
      window.addEventListener('online', handleOnline);
      window.addEventListener('offline', handleOffline);
      return () => {
        window.removeEventListener('online', handleOnline);
        window.removeEventListener('offline', handleOffline);
      };
    }, []);

    // WebSocket live session connection for collaboration
    useEffect(() => {
      if (user && currentView === "dashboard") {
        const ws = new WebSocket(`ws://localhost:8000/ws/collaborate/session_hyperlytics`);
        ws.onopen = () => {
          console.log("Collaborative WS open");
          ws.send(JSON.stringify({ type: "join", user: user.name }));
        };
        ws.onmessage = (e) => {
          try {
            const msg = JSON.parse(e.data);
            if (msg.type === "lock") {
              setQueryLock(msg.lockedBy);
            } else if (msg.type === "unlock") {
              setQueryLock(null);
            }
          } catch (err) {
            console.error("WS error:", err);
          }
        };
        setWsConnection(ws);
        return () => ws.close();
      }
    }, [user, currentView]);

    // Ingest data health and domain suggested chips
    useEffect(() => {
      if (selectedDataset) {
        fetch(`${API_URL}/api/datasets/fingerprint`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ dataset_name: selectedDataset })
        })
        .then(res => res.json())
        .then(data => {
          if (data.success) {
            setDatasetFingerprint(data);
          }
        })
        .catch(err => console.error("Fingerprint profile failed:", err));
      } else {
        setDatasetFingerprint(null);
      }
    }, [selectedDataset]);

    // ===== DASHBOARD GRID ENGINE =====
    const fetchDashboard = async (datasetName: string) => {
      setDashboardLoading(true);
      try {
        const res = await fetch(`${API_URL}/api/dashboard/${encodeURIComponent(datasetName)}`, {
          headers: user ? { "X-User-Id": user.id } : {}
        });
        if (res.ok) {
          const data: DashboardConfig = await res.json();
          setDashboardConfig(data);
          setLocalWidgets(data.widgets);
          setGlobalFilters({});
          setCrossFilters({});
        }
      } catch (err) {
        console.error("Failed to fetch dashboard:", err);
      } finally {
        setDashboardLoading(false);
      }
    };

    const fetchWidgetData = async (
      datasetName: string,
      widget: DashboardWidget,
      gFilters: { [col: string]: string[] },
      cFilters: { [col: string]: string[] }
    ) => {
      setWidgetsLoading(prev => ({ ...prev, [widget.id]: true }));
      const mergedFilters: { [col: string]: string[] } = {};
      for (const [k, v] of Object.entries(gFilters)) {
        if (v.length > 0) mergedFilters[k] = v;
      }
      for (const [k, v] of Object.entries(cFilters)) {
        if (v.length > 0) {
          mergedFilters[k] = mergedFilters[k] ? [...new Set([...mergedFilters[k], ...v])] : v;
        }
      }
      const isKpi = widget.type === "KPI_CARD";
      const params = new URLSearchParams({
        dataset_name: datasetName,
        x_col: widget.data_binding.x_col,
        is_kpi: String(isKpi),
        limit: "15"
      });
      if (widget.data_binding.y_col && widget.data_binding.y_col !== "null") {
        params.set("y_col", String(widget.data_binding.y_col));
      }
      if (widget.data_binding.aggregation) {
        params.set("aggregation", widget.data_binding.aggregation);
      }
      if (Object.keys(mergedFilters).length > 0) {
        params.set("filters", JSON.stringify(mergedFilters));
      }
      try {
        const res = await fetch(`${API_URL}/api/dashboard/query-widget?${params.toString()}`);
        if (res.ok) {
          const data = await res.json();
          setWidgetsData(prev => ({ ...prev, [widget.id]: data }));
        }
      } catch (err) {
        console.error(`Widget ${widget.id} query failed:`, err);
      } finally {
        setWidgetsLoading(prev => ({ ...prev, [widget.id]: false }));
      }
    };

    const fetchAllWidgets = (
      datasetName: string,
      widgets: DashboardWidget[],
      gf: { [col: string]: string[] },
      cf: { [col: string]: string[] }
    ) => {
      widgets.forEach(w => fetchWidgetData(datasetName, w, gf, cf));
    };

    useEffect(() => {
      if (selectedDataset && activeTab === "command") {
        fetchDashboard(selectedDataset);
      }
    }, [selectedDataset, activeTab]);

    useEffect(() => {
      if (dashboardConfig && selectedDataset && localWidgets.length > 0) {
        fetchAllWidgets(selectedDataset, localWidgets, globalFilters, crossFilters);
      }
    }, [dashboardConfig, globalFilters, crossFilters]);

    const toggleGlobalFilter = (col: string, val: string) => {
      setGlobalFilters(prev => {
        const current = prev[col] || [];
        const updated = current.includes(val) ? current.filter(v => v !== val) : [...current, val];
        return { ...prev, [col]: updated };
      });
    };

    const handleCrossFilter = (col: string, val: string) => {
      setCrossFilters(prev => {
        const current = prev[col] || [];
        if (current.includes(val)) {
          const updated = current.filter(v => v !== val);
          const newFilters = { ...prev, [col]: updated };
          if (updated.length === 0) delete newFilters[col];
          return newFilters;
        }
        return { ...prev, [col]: [val] };
      });
    };

    const clearAllFilters = () => {
      setGlobalFilters({});
      setCrossFilters({});
    };

    const saveDashboardLayout = async () => {
      if (!dashboardConfig || !selectedDataset) return;
      setSavingLayout(true);
      try {
        const res = await fetch(`${API_URL}/api/dashboard/save`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(user ? { "X-User-Id": user.id } : {})
          },
          body: JSON.stringify({
            dataset_name: selectedDataset,
            title: dashboardConfig.title,
            widgets: localWidgets,
            theme: dashboardConfig.theme
          })
        });
        if (res.ok) {
          setSuccessMsg("Dashboard layout saved successfully!");
          setTimeout(() => setSuccessMsg(null), 3000);
        }
      } catch (err) {
        console.error("Failed to save dashboard:", err);
      } finally {
        setSavingLayout(false);
      }
    };

    // Drag and resize handlers
    const handleDragStart = (widgetId: string, e: React.MouseEvent) => {
      e.preventDefault();
      const widget = localWidgets.find(w => w.id === widgetId);
      if (!widget) return;
      setActiveDragId(widgetId);
      dragStartRef.current = { mx: e.pageX, my: e.pageY, ox: widget.x, oy: widget.y };
    };

    const handleResizeStart = (widgetId: string, e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      const widget = localWidgets.find(w => w.id === widgetId);
      if (!widget) return;
      setActiveResizeId(widgetId);
      resizeStartRef.current = { mx: e.pageX, my: e.pageY, ow: widget.w, oh: widget.h };
    };

    useEffect(() => {
      const onMouseMove = (e: MouseEvent) => {
        if (activeDragId && dragStartRef.current && gridContainerRef.current) {
          const rect = gridContainerRef.current.getBoundingClientRect();
          const colW = rect.width / 12;
          const rowH = 90;
          const dx = e.pageX - dragStartRef.current.mx;
          const dy = e.pageY - dragStartRef.current.my;
          const newX = Math.max(0, Math.round(dragStartRef.current.ox + dx / colW));
          const newY = Math.max(0, Math.round(dragStartRef.current.oy + dy / rowH));
          setLocalWidgets(prev => prev.map(w => {
            if (w.id !== activeDragId) return w;
            return { ...w, x: Math.min(newX, 12 - w.w), y: newY };
          }));
        }
        if (activeResizeId && resizeStartRef.current && gridContainerRef.current) {
          const rect = gridContainerRef.current.getBoundingClientRect();
          const colW = rect.width / 12;
          const rowH = 90;
          const dx = e.pageX - resizeStartRef.current.mx;
          const dy = e.pageY - resizeStartRef.current.my;
          const newW = Math.max(2, Math.round(resizeStartRef.current.ow + dx / colW));
          const newH = Math.max(2, Math.round(resizeStartRef.current.oh + dy / rowH));
          setLocalWidgets(prev => prev.map(w => {
            if (w.id !== activeResizeId) return w;
            return { ...w, w: Math.min(newW, 12 - w.x), h: newH };
          }));
        }
      };
      const onMouseUp = () => {
        setActiveDragId(null);
        setActiveResizeId(null);
        dragStartRef.current = null;
        resizeStartRef.current = null;
      };
      if (activeDragId || activeResizeId) {
        window.addEventListener("mousemove", onMouseMove);
        window.addEventListener("mouseup", onMouseUp);
      }
      return () => {
        window.removeEventListener("mousemove", onMouseMove);
        window.removeEventListener("mouseup", onMouseUp);
      };
    }, [activeDragId, activeResizeId]);

    const getWidgetStyle = (w: DashboardWidget): React.CSSProperties => ({
      position: "absolute" as const,
      left: `${(w.x / 12) * 100}%`,
      top: `${w.y * 90}px`,
      width: `${(w.w / 12) * 100}%`,
      height: `${w.h * 90 - 12}px`,
      padding: "4px",
      boxSizing: "border-box" as const,
      transition: (activeDragId === w.id || activeResizeId === w.id) ? "none" : "all 0.2s ease",
      zIndex: (activeDragId === w.id || activeResizeId === w.id) ? 50 : 1,
    });

    const gridHeight = localWidgets.length > 0
      ? Math.max(...localWidgets.map(w => (w.y + w.h) * 90)) + 12
      : 400;

    const renderWidgetContent = (widget: DashboardWidget) => {
      const wData = widgetsData[widget.id];
      const wLoading = widgetsLoading[widget.id];
      if (wLoading) {
        return <div className="flex items-center justify-center h-full"><RefreshCw className="w-5 h-5 text-primary animate-spin" /></div>;
      }
      if (!wData || wData.length === 0) {
        return <div className="flex items-center justify-center h-full text-[10px] text-slate-400">No data</div>;
      }
      if (widget.type === "KPI_CARD") {
        const val = wData[0]?.y;
        const display = typeof val === "number"
          ? (val > 999999 ? `${(val / 1000000).toFixed(1)}M` : val > 999 ? `${(val / 1000).toFixed(1)}K` : val % 1 === 0 ? val.toLocaleString() : Number(val).toFixed(2))
          : String(val ?? "\u2014");
        return <div className="flex flex-col items-center justify-center h-full"><span className="text-3xl font-black text-slate-800 tracking-tight">{display}</span></div>;
      }
      if (widget.type === "BAR_CHART") {
        return (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={wData}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.04)" />
              <XAxis dataKey="x" stroke="#94a3b8" tick={{ fontSize: 9 }} />
              <YAxis stroke="#94a3b8" tick={{ fontSize: 9 }} />
              <Tooltip contentStyle={{ backgroundColor: "#fff", borderColor: "#e2e8f0", fontSize: 10 }} />
              <Bar dataKey="y" fill="#4F46E5" radius={[4, 4, 0, 0]} cursor="pointer" onClick={(data: any) => { if (data?.x) handleCrossFilter(widget.data_binding.x_col, String(data.x)); }} />
            </BarChart>
          </ResponsiveContainer>
        );
      }
      if (widget.type === "AREA_CHART") {
        return (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={wData}>
              <defs><linearGradient id={`grad-${widget.id}`} x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#0EA5E9" stopOpacity={0.3} /><stop offset="95%" stopColor="#0EA5E9" stopOpacity={0} /></linearGradient></defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.04)" />
              <XAxis dataKey="x" stroke="#94a3b8" tick={{ fontSize: 9 }} />
              <YAxis stroke="#94a3b8" tick={{ fontSize: 9 }} />
              <Tooltip contentStyle={{ backgroundColor: "#fff", borderColor: "#e2e8f0", fontSize: 10 }} />
              <Area type="monotone" dataKey="y" stroke="#0EA5E9" strokeWidth={2} fill={`url(#grad-${widget.id})`} />
            </AreaChart>
          </ResponsiveContainer>
        );
      }
      if (widget.type === "PIE_CHART") {
        return (
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={wData} dataKey="y" nameKey="x" cx="50%" cy="50%" outerRadius="70%" innerRadius="40%" paddingAngle={2} cursor="pointer" onClick={(data: any) => { if (data?.x) handleCrossFilter(widget.data_binding.x_col, String(data.x)); }}>
                {wData.map((_: any, idx: number) => <Cell key={idx} fill={DASHBOARD_COLORS[idx % DASHBOARD_COLORS.length]} />)}
              </Pie>
              <Tooltip contentStyle={{ backgroundColor: "#fff", borderColor: "#e2e8f0", fontSize: 10 }} />
              <Legend verticalAlign="bottom" height={24} iconSize={8} wrapperStyle={{ fontSize: 9 }} />
            </PieChart>
          </ResponsiveContainer>
        );
      }
      if (widget.type === "TABLE") {
        return (
          <div className="overflow-auto h-full border border-slate-200 rounded-lg bg-white">
            <table className="w-full text-left border-collapse text-[10px]">
              <thead><tr className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase tracking-wider sticky top-0">
                <th className="p-2 font-semibold">{widget.data_binding.x_col}</th>
                <th className="p-2 font-semibold">{widget.data_binding.aggregation}({widget.data_binding.y_col || widget.data_binding.x_col})</th>
              </tr></thead>
              <tbody>
                {wData.map((row: any, idx: number) => (
                  <tr key={idx} className="border-b border-slate-100 hover:bg-slate-50 text-slate-700 cursor-pointer" onClick={() => handleCrossFilter(widget.data_binding.x_col, String(row.x))}>
                    <td className="p-2 font-mono">{String(row.x)}</td>
                    <td className="p-2 font-mono">{typeof row.y === "number" ? row.y.toLocaleString() : String(row.y)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      }
      return <div className="text-[10px] text-slate-400 flex items-center justify-center h-full">Unsupported widget</div>;
    };

    const activeFilterCount = Object.values(globalFilters).reduce((a, b) => a + b.length, 0) + Object.values(crossFilters).reduce((a, b) => a + b.length, 0);

    const fetchAuditLogs = async () => {
      if (!user) return;
      try {
        const res = await fetch(`${API_URL}/api/admin/audit`, {
          headers: {
            "X-User-Id": user.id
          }
        });
        if (res.ok) {
          const data = await res.json();
          setAuditLogs(data);
        }
      } catch (err) {
        console.error("Failed to fetch compliance logs:", err);
      }
    };

    useEffect(() => {
      if (activeTab === "audit") {
        fetchAuditLogs();
      }
    }, [activeTab]);

    // Offline queue automatic sync when online
    useEffect(() => {
      if (isOnline && offlineQueue.length > 0) {
        const syncOffline = async () => {
          for (const q of offlineQueue) {
            await handleChatSubmit(undefined, q.query);
          }
          setOfflineQueue([]);
          setSuccessMsg("Network connection reconnected. Queued offline queries executed successfully.");
        };
        syncOffline();
      }
    }, [isOnline, offlineQueue]);

    const generateChartNarrative = (data: any[], chartType: string, xKey?: string, yKey?: string) => {
      if (!data || data.length === 0) return "";
      
      const keys = Object.keys(data[0]);
      const x = xKey || keys[0] || "";
      
      // Guess numeric Y-axis key
      const numericKeys = keys.filter(k => {
        return data.some(row => {
          const val = row[k];
          return typeof val === "number" || (!isNaN(Number(val)) && val !== null && val !== "");
        });
      });
      const y = yKey || numericKeys[0] || keys[1] || keys[0] || "";
      
      if (!x || !y) return "";

      // Find max and min values
      let maxVal = -Infinity;
      let minVal = Infinity;
      let maxRow: any = null;
      let minRow: any = null;

      data.forEach(row => {
        const val = Number(row[y]);
        if (!isNaN(val)) {
          if (val > maxVal) { maxVal = val; maxRow = row; }
          if (val < minVal) { minVal = val; minRow = row; }
        }
      });

      if (maxVal === -Infinity || minVal === Infinity) return "";

      const readableType = chartType === "bar" ? "Bar Chart" : chartType === "line" ? "Line Chart" : chartType === "area" ? "Area Chart" : "data table";
      
      return ` For your visualization, I have generated a ${readableType} showing ${y} across ${x}. The highest value recorded is ${maxVal.toLocaleString()} on ${String(maxRow[x])}, and the lowest value is ${minVal.toLocaleString()} on ${String(minRow[x])}.`;
    };

    const speakExplanation = (text: string, chartSummary: string = "") => {
      if (isMuted) return;
      
      // Stop any active speech first
      window.speechSynthesis.cancel();
      
      // Clean technical preambles, fuzzy mappings, and markdown tags
      let cleanText = text
        .replace(/Alternate Local Engine:\s*/gi, "")
        .replace(/\(Fuzzy mapped columns:\s*\{[^}]*\}\)/gi, "")
        .replace(/Here are the (filtered )?records from '[^']+'\s*[:.]/gi, "")
        .replace(/\(Fuzzy mapped columns:[^)]+\)/gi, "")
        .replace(/```[\s\S]*?```/g, "") // remove code blocks
        .replace(/`([^`]+)`/g, "$1")     // remove inline code backticks
        .replace(/\*\*([^*]+)\*\*/g, "$1") // remove bold markdown
        .replace(/\*([^*]+)\*/g, "$1")     // remove italic markdown
        .replace(/#+\s+([^\n]+)/g, "$1")  // remove headers
        .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1") // remove markdown links
        .replace(/\n+/g, " ")             // replace newlines with space
        .trim();

      const sentenceToSpeak = cleanText + chartSummary;
      
      if (!sentenceToSpeak) return;

      const utterance = new SpeechSynthesisUtterance(sentenceToSpeak);
      
      // Automatically detect Hindi or English speech patterns
      const containsDevanagari = /[\u0900-\u097F]/.test(sentenceToSpeak);
      const containsHindiKeywords = /\b(aur|hoga|hai|tha|ki|m|pr|h|sare|dataset|forecasting|smjhaye|btado|chahiye|pe|karte|hua)\b/i.test(sentenceToSpeak);
      
      if (containsDevanagari || containsHindiKeywords) {
        utterance.lang = "hi-IN";
      } else {
        utterance.lang = "en-US";
      }
      
      window.speechSynthesis.speak(utterance);
    };

    const toggleVoiceListening = () => {
      const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      
      if (!SpeechRecognition) {
        alert("Speech recognition is not supported in this browser. Please try Google Chrome or Microsoft Edge.");
        return;
      }

      if (isListening) {
        if (recognitionRef.current) {
          recognitionRef.current.stop();
        }
        setIsListening(false);
        return;
      }

      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      
      // Attempt to support bilingual or fallback speech recognition lang
      recognition.lang = "en-US";
      
      recognition.onstart = () => {
        setIsListening(true);
      };

      recognition.onerror = (event: any) => {
        console.error("Speech recognition error:", event.error);
        setIsListening(false);
      };

      recognition.onend = () => {
        setIsListening(false);
      };

      recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        if (transcript) {
          setQuery(prev => (prev ? prev + " " + transcript : transcript));
        }
      };

      recognitionRef.current = recognition;
      recognition.start();
    };
    
    // Chat state
    const [query, setQuery] = useState<string>("");
    const [chatHistory, setChatHistory] = useState<Message[]>([
      {
        role: "ai",
        content: "System Initialized. Accessing Hyperlytics AI Gateway. Select a dataset and ask your data anything, run statistical queries, or generate model forecasts."
      }
    ]);
    
    // File upload state
    const [dragActive, setDragActive] = useState<boolean>(false);
    const fileInputRef = useRef<HTMLInputElement>(null);
    
    // Forecasting config
    const [dateColumn, setDateColumn] = useState<string>("");
    const [targetColumn, setTargetColumn] = useState<string>("");
    const [horizon, setHorizon] = useState<number>(30);
    const [forecastResult, setForecastResult] = useState<any>(null);

    const fetchChatHistory = async () => {
      try {
        const url = user?.id 
          ? `${API_URL}/api/chat?user_id=${encodeURIComponent(user.id)}`
          : `${API_URL}/api/chat`;
        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          if (data && data.length > 0) {
            setChatHistory(data);
          } else {
            // Reset to default greeting if history is empty
            setChatHistory([
              {
                role: "ai",
                content: "System Initialized. Accessing Hyperlytics AI Gateway. Select a dataset and ask your data anything, run statistical queries, or generate model forecasts."
              }
            ]);
          }
        }
      } catch (err) {
        console.error("Failed to load chat history:", err);
      }
    };

    const clearChat = async () => {
      if (!confirm("Are you sure you want to clear your chat history?")) return;
      try {
        const url = user?.id 
          ? `${API_URL}/api/chat?user_id=${encodeURIComponent(user.id)}`
          : `${API_URL}/api/chat`;
        const res = await fetch(url, { method: "DELETE" });
        if (res.ok) {
          setChatHistory([
            {
              role: "ai",
              content: "System Initialized. Accessing Hyperlytics AI Gateway. Select a dataset and ask your data anything, run statistical queries, or generate model forecasts."
            }
          ]);
        }
      } catch (err) {
        console.error("Failed to clear chat history:", err);
      }
    };

    useEffect(() => {
      fetchDatasets();
      fetchChatHistory();
    }, [user]);

    useEffect(() => {
      if (selectedDataset) {
        fetchSchema(selectedDataset);
      } else {
        setSchemaData(null);
      }
    }, [selectedDataset]);

    const fetchDatasets = async () => {
      try {
        const res = await fetch(`${API_URL}/api/datasets`);
        if (res.ok) {
          const data = await res.json();
          setDatasets(data);
          if (data.length > 0 && !selectedDataset) {
            setSelectedDataset(data[0].name);
          }
        }
      } catch (err) {
        console.error("Failed to load datasets:", err);
      }
    };

    const fetchSchema = async (name: string) => {
      const headers: any = { "Content-Type": "application/json" };
      const oKey = localStorage.getItem("openaiKey");
      const aKey = localStorage.getItem("anthropicKey");
      const grKey = localStorage.getItem("groqKey");
      const gemKey = localStorage.getItem("geminiKey");
      if (oKey) headers["X-OpenAI-Key"] = oKey;
      if (aKey) headers["X-Anthropic-Key"] = aKey;
      if (grKey) headers["X-Groq-Key"] = grKey;
      if (gemKey) headers["X-Gemini-Key"] = gemKey;

      try {
        const res = await fetch(`${API_URL}/api/query`, {
          method: "POST",
          headers,
          body: JSON.stringify({ query: `describe ${name}`, dataset_name: name })
        });
        if (res.ok) {
          const result = await res.json();
          if (result.data && !result.data.error) {
            setSchemaData(result.data);
            const cols = result.data.columns || [];
            if (cols.length > 0) {
              const dtCol = cols.find((c: any) => c.column.toLowerCase().includes("date") || c.column.toLowerCase().includes("time"));
              const numCol = cols.find((c: any) => ["INTEGER", "BIGINT", "DOUBLE", "FLOAT", "DECIMAL"].includes(c.type.toUpperCase()));
              setDateColumn(dtCol ? dtCol.column : cols[0].column);
              setTargetColumn(numCol ? numCol.column : (cols[1] ? cols[1].column : cols[0].column));
            }
          }
        }
      } catch (err) {
        console.error("Failed to load schema:", err);
      }
    };

    const handleDrag = (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (e.type === "dragenter" || e.type === "dragover") setDragActive(true);
      else if (e.type === "dragleave") setDragActive(false);
    };

    const handleDrop = async (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragActive(false);
      if (e.dataTransfer.files && e.dataTransfer.files[0]) {
        await uploadFile(e.dataTransfer.files[0]);
      }
    };

    const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files && e.target.files[0]) {
        await uploadFile(e.target.files[0]);
      }
    };

    const uploadFile = async (file: File) => {
      setLoading(true);
      setError(null);
      setSuccessMsg(null);
      setDriftWarning(null);
      const formData = new FormData();
      formData.append("file", file);
      try {
        const res = await fetch(`${API_URL}/api/upload`, { method: "POST", body: formData });
        const data = await res.json();
        if (res.ok) {
          setSuccessMsg(`File "${file.name}" uploaded successfully!`);
          if (data.drift_report && data.drift_report.drift_detected) {
            setDriftWarning(data.drift_report);
          }
          await fetchDatasets();
          setSelectedDataset(file.name);
        } else {
          setError(data.detail || "Failed to upload file.");
        }
      } catch (err) {
        setError("Server connection failed. Make sure the backend is running.");
      } finally {
        setLoading(false);
      }
    };

    const handleGenerateStory = async (msgIdx: number, queryText: string, resultData: any[], chartConfig: any) => {
      setNarrativeLoading(msgIdx);
      const headers: any = { "Content-Type": "application/json" };
      const oKey = localStorage.getItem("openaiKey");
      const aKey = localStorage.getItem("anthropicKey");
      const grKey = localStorage.getItem("groqKey");
      const gemKey = localStorage.getItem("geminiKey");
      if (oKey) headers["X-OpenAI-Key"] = oKey;
      if (aKey) headers["X-Anthropic-Key"] = aKey;
      if (grKey) headers["X-Groq-Key"] = grKey;
      if (gemKey) headers["X-Gemini-Key"] = gemKey;

      try {
        const res = await fetch(`${API_URL}/api/query/explain`, {
          method: "POST",
          headers,
          body: JSON.stringify({
            query_text: queryText,
            result_data: resultData,
            chart_config: chartConfig,
            language: "en",
            user_id: user?.id || "default_user"
          })
        });
        if (res.ok) {
          const data = await res.json();
          // Now create a share link automatically as well to populate share_id and URLs!
          const shareRes = await fetch(`${API_URL}/api/query/share`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              user_id: user?.id || "default_user",
              query_text: queryText,
              chart_config: chartConfig,
              result_data: resultData,
              story_text: data.story
            })
          });
          if (shareRes.ok) {
            const shareData = await shareRes.json();
            setStoryNarratives(prev => ({
              ...prev,
              [msgIdx]: {
                ...data.story,
                share_id: shareData.share_id,
                image_url: shareData.image_url,
                pdf_url: shareData.pdf_url,
                share_url: shareData.share_url
              }
            }));
          } else {
            setStoryNarratives(prev => ({
              ...prev,
              [msgIdx]: data.story
            }));
          }
        }
      } catch (err) {
        console.error("Failed to generate data story:", err);
      } finally {
        setNarrativeLoading(null);
      }
    };

    const deleteDataset = async (name: string) => {
      if (!confirm(`Are you sure you want to delete dataset "${name}"?`)) return;
      try {
        const res = await fetch(`${API_URL}/api/datasets/${name}`, { method: "DELETE" });
        if (res.ok) {
          setSuccessMsg(`Dataset "${name}" deleted.`);
          if (selectedDataset === name) setSelectedDataset("");
          await fetchDatasets();
        }
      } catch (err) {
        setError("Failed to delete dataset.");
      }
    };

    const handleChatSubmit = async (e?: React.FormEvent, overrideQuery?: string) => {
      if (e) e.preventDefault();
      const userMsg = overrideQuery !== undefined ? overrideQuery : query;
      if (!userMsg.trim()) return;
      
      if (overrideQuery === undefined) {
        setQuery("");
      }
      setLastQueryText(userMsg);
      
      const userMessage: Message = { role: "user", content: userMsg, user_id: user?.id || undefined };
      setChatHistory(prev => [...prev, userMessage]);

      if (!navigator.onLine) {
        const offlineMsg: Message = { 
          role: "ai", 
          content: `Workspace Offline Mode. Your query has been cached to the local sync queue and will execute automatically when network connection is established. Last cached schema columns: ${schemaData?.columns?.map((c: any) => c.column).join(", ") || "N/A"}.` 
        };
        setChatHistory(prev => [...prev, offlineMsg]);
        setOfflineQueue(prev => [...prev, { query: userMsg, dataset_name: selectedDataset }]);
        setLoading(false);
        return;
      }

      setLoading(true);

      // Save user message to database
      try {
        await fetch(`${API_URL}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(userMessage)
        });
      } catch (err) {
        console.error("Failed to save user message to chat history:", err);
      }

      const headers: any = { "Content-Type": "application/json" };
      const oKey = localStorage.getItem("openaiKey");
      const aKey = localStorage.getItem("anthropicKey");
      const grKey = localStorage.getItem("groqKey");
      const gemKey = localStorage.getItem("geminiKey");
      if (oKey) headers["X-OpenAI-Key"] = oKey;
      if (aKey) headers["X-Anthropic-Key"] = aKey;
      if (grKey) headers["X-Groq-Key"] = grKey;
      if (gemKey) headers["X-Gemini-Key"] = gemKey;

      let hasCreatedAiMessage = false;
      let finalContent = "";
      let finalSql: string | undefined = undefined;
      let finalChart: any = null;
      let finalData: any[] | null = null;
      let finalConfidenceReport: any = null;

      try {
        const res = await fetch(`${API_URL}/api/query/stream`, {
          method: "POST",
          headers,
          body: JSON.stringify({ 
            query: userMsg, 
            dataset_name: selectedDataset || null,
            user_id: user?.id || null
          })
        });
        
        if (!res.ok) {
          const errText = await res.text();
          throw new Error(errText || "Failed to execute query stream.");
        }
        
        const reader = res.body?.getReader();
        const decoder = new TextDecoder("utf-8");
        if (!reader) throw new Error("Stream reader not supported.");
        
        // Insert initial empty AI message
        setChatHistory(prev => [...prev, { role: "ai", content: "", sql: undefined, chart: null, data: null, confidence_report: null }]);
        hasCreatedAiMessage = true;
        
        let buffer = "";
        
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n\n");
          buffer = lines.pop() || "";
          
          for (const line of lines) {
            if (line.trim().startsWith("data: ")) {
              const jsonStr = line.replace("data: ", "").trim();
              try {
                const event = JSON.parse(jsonStr);
                if (event.type === "token") {
                  const chunk = event.content || "";
                  finalContent += chunk;
                  setChatHistory(prev => {
                    const updated = [...prev];
                    const last = updated[updated.length - 1];
                    if (last && last.role === "ai") {
                      last.content = finalContent;
                    }
                    return updated;
                  });
                } else if (event.type === "sql") {
                  finalSql = event.content;
                  setChatHistory(prev => {
                    const updated = [...prev];
                    const last = updated[updated.length - 1];
                    if (last && last.role === "ai") {
                      last.sql = finalSql;
                    }
                    return updated;
                  });
                } else if (event.type === "chart") {
                  finalChart = event.content;
                  setChatHistory(prev => {
                    const updated = [...prev];
                    const last = updated[updated.length - 1];
                    if (last && last.role === "ai") {
                      last.chart = finalChart;
                    }
                    return updated;
                  });
                } else if (event.type === "data") {
                  finalData = event.content;
                  setChatHistory(prev => {
                    const updated = [...prev];
                    const last = updated[updated.length - 1];
                    if (last && last.role === "ai") {
                      last.data = finalData;
                    }
                    return updated;
                  });
                } else if (event.type === "confidence_report") {
                  finalConfidenceReport = event.content;
                  setChatHistory(prev => {
                    const updated = [...prev];
                    const last = updated[updated.length - 1];
                    if (last && last.role === "ai") {
                      last.confidence_report = finalConfidenceReport;
                    }
                    return updated;
                  });
                  
                  // Auto-trigger modal if overall_score is below 50%
                  if (finalConfidenceReport && finalConfidenceReport.overall_score < 0.50) {
                    setCorrectionReport(finalConfidenceReport);
                    setCorrectingDataset(selectedDataset);
                    
                    const initialMapping: { [token: string]: string } = {};
                    finalConfidenceReport.column_mappings.forEach((m: any) => {
                      initialMapping[m.query_token] = m.matched_column;
                    });
                    setAliasCorrections(initialMapping);
                    setCorrectionModalOpen(true);
                  }
                }
              } catch (e) {
                console.error("Error parsing stream event:", e);
              }
            }
          }
        }
        
        // Once the stream completes, save the entire AI message to the database
        const completedAiMessage: Message = {
          role: "ai",
          content: finalContent || "Analysis complete.",
          sql: finalSql,
          chart: finalChart,
          data: finalData,
          confidence_report: finalConfidenceReport,
          user_id: user?.id || undefined
        };
        
        try {
          await fetch(`${API_URL}/api/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(completedAiMessage)
          });
        } catch (err) {
          console.error("Failed to save AI message to database:", err);
        }

        // Trigger dynamic visual and text narration
        let chartSummaryText = "";
        if (finalData && finalData.length > 0) {
          chartSummaryText = generateChartNarrative(
            finalData, 
            finalChart?.type || "table", 
            finalChart?.x, 
            finalChart?.y
          );
        }
        speakExplanation(completedAiMessage.content, chartSummaryText);
      } catch (err: any) {
        const errorText = err.message || String(err);
        const errMessageContent = `API Gateway error: ${errorText}. Please verify that the FastAPI backend server is running.`;
        
        if (hasCreatedAiMessage) {
          setChatHistory(prev => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last && last.role === "ai") {
              last.content = errMessageContent;
            }
            return updated;
          });
          
          try {
            await fetch(`${API_URL}/api/chat`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ role: "ai", content: errMessageContent, user_id: user?.id || undefined })
            });
          } catch (dbErr) {
            console.error("Failed to save AI error message to database:", dbErr);
          }
        } else {
          const networkErrorMessage: Message = {
            role: "ai",
            content: errMessageContent,
            user_id: user?.id || undefined
          };
          setChatHistory(prev => [...prev, networkErrorMessage]);
          try {
            await fetch(`${API_URL}/api/chat`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(networkErrorMessage)
            });
          } catch (dbErr) {
            console.error("Failed to save AI network error message to chat history:", dbErr);
          }
        }
      } finally {
        setLoading(false);
      }
    };

    const runForecasting = async () => {
      if (!selectedDataset || !dateColumn || !targetColumn) return;
      setLoading(true);
      setForecastResult(null);
      setError(null);

      const headers: any = { "Content-Type": "application/json" };
      const oKey = localStorage.getItem("openaiKey");
      const aKey = localStorage.getItem("anthropicKey");
      const grKey = localStorage.getItem("groqKey");
      const gemKey = localStorage.getItem("geminiKey");
      if (oKey) headers["X-OpenAI-Key"] = oKey;
      if (aKey) headers["X-Anthropic-Key"] = aKey;
      if (grKey) headers["X-Groq-Key"] = grKey;
      if (gemKey) headers["X-Gemini-Key"] = gemKey;

      try {
        const res = await fetch(`${API_URL}/api/query`, {
          method: "POST",
          headers,
          body: JSON.stringify({ 
            query: `forecast ${targetColumn} over ${dateColumn} for ${horizon} days`, 
            dataset_name: selectedDataset,
            forecast_config: {
              model_type: forecastingModel,
              seasonality_mode: seasonalityMode,
              clean_outliers: cleanOutliers,
              fill_method: fillMethod,
              confidence_level: confidenceLevel
            }
          })
        });
        const data = await res.json();
        if (res.ok && data.data && !data.data.error) {
          setForecastResult(data.data);
        } else {
          setError(data.data?.error || data.response || "Failed to compile forecast model.");
        }
      } catch (err) {
        setError("Connection to forecasting engine failed.");
      } finally {
        setLoading(false);
      }
    };


    return (
      <div className="flex min-h-screen bg-background grid-bg text-foreground w-full">
        {/* Left Sidebar */}
        <aside className="w-64 border-r border-slate-200 bg-white flex flex-col justify-between p-4 z-10 shrink-0">
          <div>
            {user ? (
              <div className="flex flex-col gap-3 mb-6 p-3.5 rounded-xl bg-slate-50 border border-slate-200/80 shadow-sm relative overflow-hidden group">
                <div className="flex items-center gap-2.5">
                  {user.picture ? (
                    <img 
                      src={user.picture} 
                      alt={user.name} 
                      className="w-10 h-10 rounded-full border border-slate-200/80 object-cover shrink-0" 
                    />
                  ) : (
                    <div className="w-10 h-10 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center text-primary font-black text-xs shrink-0">
                      {user.name.slice(0, 2).toUpperCase()}
                    </div>
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-bold text-slate-800 truncate m-0 leading-tight">{user.name}</p>
                    <p className="text-[10px] text-slate-400 font-medium truncate m-0 mt-0.5 leading-none">{user.email}</p>
                  </div>
                </div>
                <div className="pt-2 border-t border-slate-200/60 flex items-center justify-between">
                  <span className="text-[9px] uppercase font-black text-slate-400 tracking-wider flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-accent-green animate-pulse"></span>
                    Verified Session
                  </span>
                  <button 
                    onClick={handleLogout}
                    title="Log Out"
                    className="p-1 rounded hover:bg-red-50 hover:text-red-600 text-slate-400 border-0 bg-transparent transition-colors cursor-pointer flex items-center justify-center"
                  >
                    <LogOut className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-between mb-6 px-2">
                <div className="flex items-center gap-2">
                  <div className="p-2 rounded bg-primary/10 border border-primary/20 animate-pulse-glow">
                    <Cpu className="w-5 h-5 text-primary" />
                  </div>
                  <div>
                    <h1 className="text-sm font-black tracking-wider text-slate-800">HYPERLYTICS</h1>
                    <span className="text-[10px] text-slate-400 uppercase tracking-widest font-bold">OS v2.0</span>
                  </div>
                </div>
                <button 
                  onClick={handleLogout}
                  title="Log Out"
                  className="p-1 rounded hover:bg-red-50 hover:text-red-600 text-slate-400 border-0 bg-transparent transition-colors cursor-pointer flex items-center justify-center"
                >
                  <LogOut className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
            <nav className="space-y-1">
              <button onClick={() => setActiveTab("command")} className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-semibold tracking-wide transition-all border-0 bg-transparent text-left cursor-pointer ${activeTab === "command" ? "bg-primary/10 text-primary" : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"}`}>
                <Layers className="w-4 h-4 text-primary" /> Command Center
              </button>
              <button onClick={() => setActiveTab("datasets")} className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-semibold tracking-wide transition-all border-0 bg-transparent text-left cursor-pointer ${activeTab === "datasets" ? "bg-primary/10 text-primary" : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"}`}>
                <Database className="w-4 h-4 text-secondary" /> Dataset Manager
              </button>
              <button onClick={() => setActiveTab("chat")} className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-semibold tracking-wide transition-all border-0 bg-transparent text-left cursor-pointer ${activeTab === "chat" ? "bg-primary/10 text-primary" : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"}`}>
                <Sparkles className="w-4 h-4 text-purple-600" /> AI Chat Assistant
              </button>
              <button onClick={() => setActiveTab("forecasting")} className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-semibold tracking-wide transition-all border-0 bg-transparent text-left cursor-pointer ${activeTab === "forecasting" ? "bg-primary/10 text-primary" : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"}`}>
                <LineIcon className="w-4 h-4 text-accent-green" /> Forecasting Center
              </button>
              {user && user.role === "ADMIN" && (
                <button onClick={() => setActiveTab("audit")} className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-semibold tracking-wide transition-all border-0 bg-transparent text-left cursor-pointer ${activeTab === "audit" ? "bg-primary/10 text-primary" : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"}`}>
                  <Shield className="w-4 h-4 text-red-600" /> Compliance Audits
                </button>
              )}
            </nav>
          </div>
          <div className="space-y-4">
            <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 text-xs">
              <div className="flex items-center gap-2 mb-1.5">
                <span className="w-2 h-2 rounded-full bg-accent-green animate-ping"></span>
                <span className="text-[10px] uppercase font-bold text-slate-500">Gateway Matrix</span>
              </div>
              <p className="text-[10px] text-slate-400 m-0">DuckDB Node: <span className="text-secondary font-bold">Ready</span></p>
            </div>
          </div>
        </aside>

        {/* Main Board */}
        <main className="flex-grow flex flex-col min-h-screen overflow-y-auto">
          <header className="h-16 border-b border-slate-200 bg-white/70 backdrop-blur-md px-6 flex items-center justify-between z-10 shrink-0">
            <div className="flex items-center gap-4">
              <span className="text-xs text-slate-400 uppercase tracking-widest font-bold">Active Workspace</span>
              <div className="relative">
                <select value={selectedDataset} onChange={(e) => setSelectedDataset(e.target.value)} className="bg-slate-50 border border-slate-200 text-xs text-slate-700 px-3 py-1.5 rounded-md focus:outline-none focus:border-primary pr-8 appearance-none cursor-pointer">
                  {datasets.length === 0 ? <option value="">No Datasets Uploaded</option> : datasets.map((d) => <option key={d.name} value={d.name}>{d.name}</option>)}
                </select>
                <Database className="w-3.5 h-3.5 text-secondary absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              </div>
            </div>
            <div className="flex items-center gap-4 text-xs font-semibold">
              <div className="flex -space-x-1.5 overflow-hidden">
                {activeCollaborators.map((c, cIdx) => (
                  <img
                    key={cIdx}
                    src={c.picture}
                    alt={c.name}
                    title={`${c.name} is editing live`}
                    className="inline-block h-6 w-6 rounded-full ring-2 ring-white object-cover cursor-help"
                  />
                ))}
              </div>

              {queryLock ? (
                <span className="px-2.5 py-1 rounded-md border text-[9px] font-bold uppercase tracking-wider text-red-600 bg-red-50 border-red-200 flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-red-600 animate-pulse"></span>
                  Locked by {queryLock}
                </span>
              ) : (
                <button
                  onClick={() => {
                    if (wsConnection && user) {
                      wsConnection.send(JSON.stringify({ type: "lock", lockedBy: user.name }));
                      setQueryLock(user.name);
                    }
                  }}
                  className="px-2.5 py-1 rounded-md border text-[9px] font-bold uppercase tracking-wider text-emerald-600 bg-emerald-50 border-emerald-200 hover:bg-emerald-100 transition-all cursor-pointer"
                >
                  Acquire Session Lock
                </button>
              )}

              {queryLock === user?.name && (
                <button
                  onClick={() => {
                    if (wsConnection) {
                      wsConnection.send(JSON.stringify({ type: "unlock" }));
                      setQueryLock(null);
                    }
                  }}
                  className="px-2.5 py-1 rounded-md border text-[9px] font-bold uppercase tracking-wider text-slate-600 bg-slate-50 border-slate-200 hover:bg-slate-100 transition-all cursor-pointer animate-pulse"
                >
                  Release Lock
                </button>
              )}

              <span className={`px-2.5 py-1 rounded-md border text-[9px] font-bold uppercase tracking-wider flex items-center gap-1.5 ${isOnline ? "text-indigo-600 bg-indigo-50 border-indigo-200" : "text-amber-600 bg-amber-50 border-amber-200 animate-pulse"}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${isOnline ? "bg-indigo-600 animate-ping" : "bg-amber-600"}`}></span>
                {isOnline ? "Live Session: Active" : "Offline Cache Mode"}
              </span>

              <span className="px-2.5 py-1 rounded-md border text-[9px] font-bold uppercase tracking-wider text-slate-500 bg-slate-50 border-slate-200">
                Local Alternate Mode (Offline)
              </span>
            </div>
          </header>

          <div className="flex-grow p-6 max-w-7xl w-full mx-auto space-y-6">
            {error && <div className="p-3 bg-red-50 border border-red-200 rounded-lg flex items-center gap-2 text-xs text-red-600"><AlertTriangle className="w-4 h-4 text-red-500 shrink-0" /> {error}</div>}
            {successMsg && <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg flex items-center gap-2 text-xs text-emerald-600"><CheckCircle className="w-4 h-4 text-accent-green shrink-0" /> {successMsg}</div>}

            {activeTab === "command" && (
              <div className="space-y-5">
                {/* ===== AI DASHBOARD HEADER ===== */}
                <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
                  <div>
                    <h2 className="text-lg font-black text-slate-800 tracking-wide m-0">{dashboardConfig?.title || "AI Analytics Dashboard"}</h2>
                    <p className="text-[10px] text-slate-400 uppercase tracking-widest font-bold mt-0.5 m-0">Auto-Generated &middot; {localWidgets.length} Widgets &middot; 12-Column Grid</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button onClick={saveDashboardLayout} disabled={savingLayout} className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-primary/20 bg-primary/5 hover:bg-primary/10 text-xs font-bold text-primary transition-all cursor-pointer">
                      {savingLayout ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                      Save Layout
                    </button>
                    <button onClick={() => setShowMetadata(!showMetadata)} className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-xs font-semibold text-slate-600 transition-all cursor-pointer">
                      <Info className="w-3.5 h-3.5" />
                      {showMetadata ? "Hide" : "Show"} Schema
                    </button>
                  </div>
                </div>

                {/* Global Filter Bar */}
                {dashboardConfig && Object.keys(dashboardConfig.filter_options).length > 0 && (
                  <div className="cyber-card p-4 rounded-xl space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <SlidersHorizontal className="w-4 h-4 text-secondary" />
                        <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Global Filters</span>
                        {activeFilterCount > 0 && (
                          <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">{activeFilterCount} active</span>
                        )}
                      </div>
                      {activeFilterCount > 0 && (
                        <button onClick={clearAllFilters} className="text-[10px] font-bold text-red-500 hover:text-red-700 cursor-pointer bg-transparent border-0 flex items-center gap-1 transition-colors">
                          <X className="w-3 h-3" /> Clear All
                        </button>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-4">
                      {Object.entries(dashboardConfig.filter_options).map(([col, values]) => (
                        <div key={col} className="space-y-1.5">
                          <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider block">{col}</span>
                          <div className="flex flex-wrap gap-1">
                            {(values as string[]).map((v: string) => {
                              const isActive = (globalFilters[col] || []).includes(String(v));
                              return (
                                <button key={String(v)} onClick={() => toggleGlobalFilter(col, String(v))} className={`px-2 py-1 rounded-md text-[10px] font-semibold border transition-all cursor-pointer ${isActive ? "bg-primary text-white border-primary shadow-sm" : "bg-white text-slate-600 border-slate-200 hover:border-primary/30 hover:bg-primary/5"}`}>
                                  {String(v)}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Cross-Filter Status */}
                {Object.keys(crossFilters).length > 0 && (
                  <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-amber-50 border border-amber-200 text-xs">
                    <Activity className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                    <span className="text-amber-700 font-semibold">Cross-Filter:</span>
                    {Object.entries(crossFilters).map(([col, vals]) => (
                      <span key={col} className="px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 text-[10px] font-bold border border-amber-200">{col} = {vals.join(", ")}</span>
                    ))}
                    <button onClick={() => setCrossFilters({})} className="ml-auto text-[10px] font-bold text-amber-600 hover:text-amber-800 cursor-pointer bg-transparent border-0 flex items-center gap-0.5 transition-colors">
                      <X className="w-3 h-3" /> Clear
                    </button>
                  </div>
                )}

                {/* Dashboard Grid */}
                {dashboardLoading ? (
                  <div className="cyber-card p-12 rounded-xl flex flex-col items-center justify-center gap-3">
                    <RefreshCw className="w-8 h-8 text-primary animate-spin" />
                    <p className="text-xs text-slate-400 font-semibold m-0">Generating AI Dashboard...</p>
                  </div>
                ) : localWidgets.length > 0 ? (
                  <div ref={gridContainerRef} className="relative w-full select-none" style={{ height: `${gridHeight}px`, minHeight: "400px" }}>
                    {localWidgets.map((widget) => (
                      <div key={widget.id} style={getWidgetStyle(widget)}>
                        <div className={`h-full rounded-xl border bg-white shadow-sm flex flex-col overflow-hidden transition-shadow relative ${activeDragId === widget.id || activeResizeId === widget.id ? "shadow-lg border-primary/40 ring-2 ring-primary/10" : "border-slate-200 hover:shadow-md hover:border-slate-300"}`}>
                          {/* Widget Header - Drag Handle */}
                          <div className="flex items-center gap-1.5 px-3 py-2 border-b border-slate-100 bg-slate-50/80 cursor-grab active:cursor-grabbing shrink-0 select-none" onMouseDown={(e) => handleDragStart(widget.id, e)}>
                            <GripVertical className="w-3 h-3 text-slate-300" />
                            <span className="text-[10px] font-bold text-slate-600 uppercase tracking-wider truncate flex-1">{widget.title}</span>
                            <span className="text-[8px] font-bold px-1.5 py-0.5 rounded bg-slate-100 text-slate-400 border border-slate-200 uppercase shrink-0">{widget.type.replace("_", " ")}</span>
                          </div>
                          {/* Widget Content */}
                          <div className="flex-1 p-2 min-h-0 overflow-hidden">{renderWidgetContent(widget)}</div>
                          {/* Resize Handle */}
                          <div className="absolute bottom-1 right-1 w-5 h-5 flex items-center justify-center cursor-se-resize opacity-0 hover:opacity-100 transition-opacity rounded-sm bg-slate-100/80 border border-slate-200" onMouseDown={(e) => handleResizeStart(widget.id, e)}>
                            <Maximize2 className="w-2.5 h-2.5 text-slate-400" />
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="cyber-card p-8 rounded-xl text-center">
                    <LayoutDashboard className="w-12 h-12 text-slate-200 mx-auto mb-3" />
                    <p className="text-xs text-slate-400 m-0">Select a dataset to auto-generate an AI dashboard.</p>
                  </div>
                )}

                {/* Collapsible Metadata Panel */}
                {showMetadata && (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                  <div className="cyber-card p-6 rounded-xl lg:col-span-1 space-y-4">
                    <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider flex items-center gap-2 m-0"><Info className="w-4 h-4 text-secondary" /> Schema Specification</h3>
                    {schemaData ? (
                      <div className="space-y-2 max-h-96 overflow-y-auto pr-2">
                        {schemaData.columns?.map((col: any) => (
                          <div key={col.column} className="flex justify-between items-center p-2 rounded bg-slate-50 border border-slate-200">
                            <span className="text-xs text-slate-700 font-medium">{col.column}</span>
                            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-primary/10 text-primary border border-primary/20">{col.type}</span>
                          </div>
                        ))}
                      </div>
                    ) : <p className="text-xs text-slate-400 m-0">No active dataset selected.</p>}
                  </div>

                  <div className="cyber-card p-6 rounded-xl lg:col-span-2 space-y-4">
                    <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider m-0">3-Row Raw Data Snippet</h3>
                    {schemaData && schemaData.sample_data ? (
                      <div className="overflow-x-auto border border-slate-200 rounded-lg">
                        <table className="w-full text-left border-collapse text-xs">
                          <thead>
                            <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase tracking-wider">
                              {Object.keys(schemaData.sample_data[0] || {}).map((k) => <th key={k} className="p-3 font-semibold">{k}</th>)}
                            </tr>
                          </thead>
                          <tbody>
                            {schemaData.sample_data.map((row: any, idx: number) => (
                              <tr key={idx} className="border-b border-slate-100 hover:bg-slate-50 text-slate-700">
                                {Object.values(row).map((val: any, i) => <td key={i} className="p-3 font-mono">{String(val)}</td>)}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : <p className="text-xs text-slate-400 m-0">Select or upload a dataset to preview sample data.</p>}
                  </div>
                </div>
                )}
              </div>
            )}

            {activeTab === "datasets" && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div onDragEnter={handleDrag} onDragOver={handleDrag} onDragLeave={handleDrag} onDrop={handleDrop} onClick={() => fileInputRef.current?.click()} className={`cyber-card p-8 rounded-xl flex flex-col items-center justify-center text-center border-2 border-dashed transition-all cursor-pointer ${dragActive ? "border-secondary bg-secondary/5" : "border-slate-200"}`}>
                  <input type="file" ref={fileInputRef} onChange={handleFileChange} className="hidden" accept=".csv,.parquet,.xlsx,.json" />
                  <UploadCloud className="w-12 h-12 text-secondary mb-4 animate-bounce" />
                  <h3 className="text-sm font-bold text-slate-700 mb-2 m-0">Drag & Drop Dataset File</h3>
                  <p className="text-xs text-slate-400 max-w-xs mb-4">Supports CSV, Parquet, JSON, and Excel documents.</p>
                  <button className="btn-cyber px-4 py-2 text-xs font-semibold">Browse Files</button>
                </div>
                <div className="cyber-card p-6 rounded-xl space-y-4">
                  <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider flex items-center gap-2 m-0"><Database className="w-4 h-4 text-secondary" /> Active Datasets Workspace</h3>
                  <div className="space-y-2">
                    {datasets.length === 0 ? <p className="text-xs text-slate-400 m-0">No active datasets.</p> : datasets.map((d) => (
                      <div key={d.name} className="flex justify-between items-center p-3 rounded-lg bg-white border border-slate-200 hover:border-secondary/40 transition-colors">
                        <div className="flex items-center gap-3">
                          <FolderOpen className="w-4 h-4 text-primary" />
                          <div>
                            <p className="text-xs font-semibold text-slate-800 m-0">{d.name}</p>
                            <p className="text-[10px] text-slate-400 m-0">Format: {d.format} | Size: {(d.size_bytes / 1024).toFixed(2)} KB</p>
                          </div>
                        </div>
                        <button onClick={(e) => { e.stopPropagation(); deleteDataset(d.name); }} className="p-1.5 rounded hover:bg-red-50 border border-transparent hover:border-red-200 text-slate-400 hover:text-red-500 transition-colors cursor-pointer"><Trash2 className="w-3.5 h-3.5" /></button>
                      </div>
                    ))}
                  </div>
                </div>

                {driftWarning && (
                  <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-800 space-y-2 lg:col-span-2">
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="w-4.5 h-4.5 text-amber-500 shrink-0" />
                      <span className="font-bold">Schema Drift Warning!</span>
                    </div>
                    <p className="m-0 text-slate-600">The uploaded file matches an existing dataset but contains schema changes. Please review changes:</p>
                    <div className="grid grid-cols-3 gap-4 font-mono text-[9.5px] bg-white/50 p-2.5 rounded-lg border border-amber-200/50">
                      <div>
                        <span className="font-bold block text-slate-400 uppercase text-[8px]">Added columns</span>
                        {driftWarning.added.length > 0 ? driftWarning.added.map((c: string) => <div key={c} className="text-emerald-600 font-bold">+ {c}</div>) : <div className="text-slate-400">None</div>}
                      </div>
                      <div>
                        <span className="font-bold block text-slate-400 uppercase text-[8px]">Removed columns</span>
                        {driftWarning.removed.length > 0 ? driftWarning.removed.map((c: string) => <div key={c} className="text-red-500 font-bold">- {c}</div>) : <div className="text-slate-400">None</div>}
                      </div>
                      <div>
                        <span className="font-bold block text-slate-400 uppercase text-[8px]">Type mutations</span>
                        {driftWarning.type_changed.length > 0 ? driftWarning.type_changed.map((m: any) => <div key={m.column} className="text-amber-600">{m.column}: {m.old_type} → {m.new_type}</div>) : <div className="text-slate-400">None</div>}
                      </div>
                    </div>
                  </div>
                )}

                {selectedDataset && datasetFingerprint && (
                  <div className="cyber-card p-6 rounded-xl space-y-4 lg:col-span-2">
                    <div className="flex justify-between items-center border-b border-slate-100 pb-3">
                      <div className="flex items-center gap-2">
                        <Activity className="w-5 h-5 text-indigo-600 animate-pulse" />
                        <h4 className="text-xs font-black uppercase tracking-wider text-slate-800 m-0">
                          Semantic Ingestion Profile: {datasetFingerprint.domain} Domain
                        </h4>
                      </div>
                      <span className="text-[9px] font-bold uppercase px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-600 border border-indigo-100">
                        AI Classifier Active
                      </span>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                      <div className="p-3 bg-slate-50 border border-slate-200/60 rounded-xl text-center">
                        <span className="text-[9px] uppercase font-bold text-slate-400 block mb-1">Completeness</span>
                        <span className="text-sm font-black text-slate-700">{datasetFingerprint.health.completeness}%</span>
                      </div>
                      <div className="p-3 bg-slate-50 border border-slate-200/60 rounded-xl text-center">
                        <span className="text-[9px] uppercase font-bold text-slate-400 block mb-1">Duplicate Rows</span>
                        <span className="text-sm font-black text-slate-700">{datasetFingerprint.health.duplicate_count}</span>
                      </div>
                      <div className="p-3 bg-slate-50 border border-slate-200/60 rounded-xl text-center">
                        <span className="text-[9px] uppercase font-bold text-slate-400 block mb-1">Outlier Anomalies</span>
                        <span className="text-sm font-black text-slate-700">{datasetFingerprint.health.outliers_count}</span>
                      </div>
                      <div className="p-3 bg-slate-50 border border-slate-200/60 rounded-xl text-center">
                        <span className="text-[9px] uppercase font-bold text-slate-400 block mb-1">Analyzed Rows</span>
                        <span className="text-sm font-black text-slate-700">{datasetFingerprint.health.total_rows.toLocaleString()}</span>
                      </div>
                    </div>

                    <div>
                      <span className="text-[9px] uppercase font-bold text-slate-400 block mb-2">Automated Query Inferences</span>
                      <div className="flex flex-wrap gap-2">
                        {datasetFingerprint.suggestions.map((suggestion: string, sIdx: number) => (
                          <button
                            key={sIdx}
                            type="button"
                            onClick={() => {
                              setQuery(suggestion);
                              setActiveTab("chat");
                            }}
                            className="px-2.5 py-1.5 rounded-lg border border-slate-200/80 bg-white hover:bg-indigo-50/50 text-[10px] font-semibold text-slate-600 hover:text-primary transition-all cursor-pointer shadow-sm text-left hover:border-primary/20"
                          >
                            💡 {suggestion}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeTab === "chat" && (
              <div className="cyber-card rounded-xl flex flex-col h-[560px] overflow-hidden">
                <div className="px-4 py-3 border-b border-slate-200 bg-white flex justify-between items-center z-10 shrink-0">
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-purple-600" />
                    <span className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">AI Assistant Session</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        const nextMute = !isMuted;
                        setIsMuted(nextMute);
                        if (nextMute) {
                          window.speechSynthesis.cancel();
                        } else {
                          const greeting = "Voice narration enabled. System ready to speak data explanations.";
                          const utterance = new SpeechSynthesisUtterance(greeting);
                          utterance.lang = "en-US";
                          window.speechSynthesis.speak(utterance);
                        }
                      }}
                      className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded text-[10px] font-bold border transition-all cursor-pointer bg-transparent ${
                        isMuted 
                          ? "text-slate-400 border-slate-200 hover:border-slate-300 hover:text-slate-600" 
                          : "text-primary border-primary/20 bg-primary/5 hover:bg-primary/10"
                      }`}
                      title={isMuted ? "Unmute voice explanations" : "Mute voice explanations"}
                    >
                      {isMuted ? <VolumeX className="w-3.5 h-3.5" /> : <Volume2 className="w-3.5 h-3.5" />}
                      {isMuted ? "Narrate: Off" : "Narrate: On"}
                    </button>
                    <button 
                      onClick={clearChat}
                      className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-[10px] font-bold text-red-600 hover:bg-red-50 border border-transparent hover:border-red-200 transition-all cursor-pointer bg-transparent"
                    >
                      <Trash2 className="w-3.5 h-3.5" /> Clear History
                    </button>
                  </div>
                </div>
                <div className="flex-grow p-4 overflow-y-auto space-y-4 bg-slate-50/40">
                  {chatHistory.map((msg, idx) => (
                    <div key={idx} className={`flex gap-3 max-w-[85%] ${msg.role === "user" ? "ml-auto flex-row-reverse" : "mr-auto"}`}>
                      <div className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-xs font-bold overflow-hidden bg-slate-100 border border-slate-200/50">
                        {msg.role === "user" ? (
                          user?.picture ? (
                            <img src={user.picture} alt="User Avatar" className="w-full h-full object-cover" />
                          ) : (
                            <div className="w-full h-full bg-secondary text-white flex items-center justify-center font-bold text-[10px]">
                              {user?.name ? user.name.charAt(0).toUpperCase() : "U"}
                            </div>
                          )
                        ) : (
                          <div className="w-full h-full bg-primary text-white flex items-center justify-center font-bold text-[10px]">
                            AI
                          </div>
                        )}
                      </div>
                      <div className={`p-3.5 rounded-lg text-xs leading-relaxed space-y-2 border ${msg.role === "user" ? "bg-primary/5 border-primary/10 text-slate-800" : "bg-white border-slate-200 text-slate-700"}`}>
                        <p className="m-0">{msg.content}</p>
                        {msg.sql && (
                          <div className="mt-2 rounded bg-slate-900 border border-slate-800 p-2 font-mono text-[10px] text-slate-300">
                            <div className="flex items-center justify-between border-b border-slate-800 pb-1 mb-1.5 text-[9px] text-slate-500 uppercase tracking-widest"><span>Generated SQL</span><Terminal className="w-3 h-3 text-primary" /></div>
                            {msg.sql}
                          </div>
                        )}
                        {msg.role === "ai" && msg.confidence_report && (
                          <div className="mt-2 space-y-1.5 border-t border-slate-100 pt-2 text-[10px]">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-1.5">
                                <span className="font-bold text-slate-400 uppercase tracking-wider text-[9px]">Confidence:</span>
                                <span 
                                  className="px-2 py-0.5 rounded-full font-bold uppercase tracking-wider text-[8px] text-white flex items-center gap-1 shadow-sm"
                                  style={{
                                    backgroundColor: 
                                      msg.confidence_report.overall_score >= 0.90 ? "#22C55E" :
                                      msg.confidence_report.overall_score >= 0.70 ? "#00B4D8" :
                                      msg.confidence_report.overall_score >= 0.50 ? "#F59E0B" : "#EF4444"
                                  }}
                                >
                                  {Math.round(msg.confidence_report.overall_score * 100)}% - {msg.confidence_report.grade}
                                </span>
                              </div>
                              
                              {msg.confidence_report.overall_score < 0.50 && (
                                <button
                                  type="button"
                                  onClick={() => {
                                    setCorrectionReport(msg.confidence_report);
                                    setCorrectingDataset(selectedDataset);
                                    const initialMapping: { [token: string]: string } = {};
                                    msg.confidence_report.column_mappings.forEach((m: any) => {
                                      initialMapping[m.query_token] = m.matched_column;
                                    });
                                    setAliasCorrections(initialMapping);
                                    setCorrectionModalOpen(true);
                                  }}
                                  className="text-primary hover:underline border-0 bg-transparent font-bold cursor-pointer text-[9px] uppercase tracking-wider"
                                >
                                  Adjust Mappings
                                </button>
                              )}
                            </div>
                            
                            <details className="cursor-pointer group mt-1">
                              <summary className="text-[9px] text-slate-400 font-bold uppercase tracking-wider hover:text-slate-600 transition-colors select-none flex items-center gap-1 outline-none">
                                Why this confidence?
                              </summary>
                              <div className="mt-1 bg-slate-50 border border-slate-100 p-2 rounded-lg text-slate-500 font-medium space-y-1 group-open:animate-in group-open:fade-in duration-200">
                                <p className="m-0 text-slate-600 font-bold text-[9.5px]">{msg.confidence_report.explanation}</p>
                                <ul className="list-disc pl-3.5 space-y-0.5 mt-1 font-mono text-[8.5px]">
                                  <li>Fuzzy Header Match: {Math.round(msg.confidence_report.signals?.header_match * 100)}%</li>
                                  <li>Schema Coverage: {Math.round(msg.confidence_report.signals?.schema_coverage * 100)}%</li>
                                  <li>Complexity Penalty: -{Math.round((1.0 - msg.confidence_report.signals?.complexity_penalty) * 100)}%</li>
                                  <li>Historical Accuracy Proxy: {Math.round(msg.confidence_report.signals?.historical_accuracy * 100)}%</li>
                                </ul>
                              </div>
                            </details>
                          </div>
                        )}
                        {msg.chart?.lineage && (
                          <div className="mt-3 p-2.5 rounded-xl bg-slate-950/90 border border-slate-800 text-[10px] overflow-hidden" dangerouslySetInnerHTML={{ __html: msg.chart.lineage }} />
                        )}
                        {msg.data && msg.data.length > 0 && (
                          <InteractiveChart 
                            data={msg.data}
                            defaultX={msg.chart?.x}
                            defaultY={msg.chart?.y}
                            defaultType={msg.chart?.type}
                          />
                        )}
                        {msg.role === "ai" && msg.data && msg.data.length > 0 && (
                          storyNarratives[idx] ? (
                            <div className="mt-4 p-4 rounded-xl bg-slate-900 border border-slate-800 text-slate-100 space-y-3 shadow-md relative">
                              <div className="flex justify-between items-center border-b border-slate-800 pb-2 mb-2">
                                <span className="text-[10px] uppercase font-black tracking-wider text-purple-400">AI Data Story Brief</span>
                                <div className="flex items-center gap-2">
                                  <button
                                    type="button"
                                    onClick={() => {
                                      const story = storyNarratives[idx];
                                      const textToSpeak = `Observation: ${story.observation}. Insight: ${story.insight}. Recommendation: ${story.recommendation}.`;
                                      speakExplanation(textToSpeak);
                                    }}
                                    className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-all text-[9px] font-bold uppercase tracking-wider flex items-center gap-1 border border-slate-700 cursor-pointer"
                                  >
                                    <Volume2 className="w-3 h-3 text-purple-400" /> Speak Brief
                                  </button>
                                  {storyNarratives[idx].pdf_url && (
                                    <button
                                      type="button"
                                      onClick={() => window.open(`${API_URL}${storyNarratives[idx].pdf_url}`, "_blank")}
                                      className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-all text-[9px] font-bold uppercase tracking-wider flex items-center gap-1 border border-slate-700 cursor-pointer"
                                    >
                                      <FolderOpen className="w-3 h-3 text-indigo-400" /> PDF Brief
                                    </button>
                                  )}
                                </div>
                              </div>
                              <div className="space-y-2 text-[11px] leading-relaxed">
                                <p className="m-0"><strong className="text-blue-400">Observation:</strong> {storyNarratives[idx].observation}</p>
                                <p className="m-0"><strong className="text-purple-400">Insight:</strong> {storyNarratives[idx].insight}</p>
                                <p className="m-0"><strong className="text-emerald-400">Recommendation:</strong> {storyNarratives[idx].recommendation}</p>
                              </div>
                              
                              {/* Public shareable section */}
                              {storyNarratives[idx].share_url && (
                                <div className="mt-3 pt-3 border-t border-slate-800 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
                                  <div className="flex items-center gap-2 text-[10px] text-slate-400">
                                    <span className="font-bold">Share Link:</span>
                                    <code className="bg-slate-950 px-1.5 py-0.5 rounded text-purple-300 font-mono text-[9px] select-all">
                                      {`${window.location.origin}${storyNarratives[idx].share_url}`}
                                    </code>
                                    <button
                                      type="button"
                                      onClick={() => {
                                        navigator.clipboard.writeText(`${window.location.origin}${storyNarratives[idx].share_url}`);
                                        alert("Copied shareable link to clipboard!");
                                      }}
                                      className="px-1.5 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-all text-[9px] font-bold border border-slate-700 cursor-pointer"
                                    >
                                      Copy
                                    </button>
                                  </div>
                                  <div className="text-[10px] text-slate-400 flex items-center gap-1">
                                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping"></span>
                                    Pillow OG Card Cached
                                  </div>
                                </div>
                              )}

                              {/* OG Card Image Preview */}
                              {storyNarratives[idx].image_url && (
                                <div className="mt-3 border border-slate-800 rounded-lg overflow-hidden relative group">
                                  <div className="text-[8px] uppercase font-bold text-slate-500 bg-slate-950 px-2 py-1 border-b border-slate-800 flex justify-between items-center">
                                    <span>Server-Side OG Preview</span>
                                    <span>1200 x 630</span>
                                  </div>
                                  <img 
                                    src={`${API_URL}${storyNarratives[idx].image_url}`} 
                                    alt="OG Card Preview" 
                                    className="w-full aspect-[1.91/1] object-cover bg-slate-950" 
                                  />
                                </div>
                              )}
                            </div>
                          ) : (
                            <div className="mt-2.5">
                              <button
                                type="button"
                                onClick={() => {
                                  const userQuery = chatHistory[idx - 1]?.content || "Analyze the dataset";
                                  handleGenerateStory(idx, userQuery, msg.data || [], msg.chart || null);
                                }}
                                disabled={narrativeLoading === idx}
                                className="px-3 py-1.5 rounded-lg border border-purple-200 hover:border-purple-300 bg-purple-50 hover:bg-purple-100 text-[10px] font-bold text-purple-700 transition-all flex items-center gap-1.5 cursor-pointer shadow-sm disabled:opacity-50"
                              >
                                {narrativeLoading === idx ? (
                                  <>
                                    <svg className="animate-spin h-3.5 w-3.5 text-purple-700" fill="none" viewBox="0 0 24 24">
                                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                                    </svg>
                                    Analyzing Data Narrative...
                                  </>
                                ) : (
                                  <>
                                    <Sparkles className="w-3.5 h-3.5 text-purple-600" />
                                    Generate AI Data Story Brief
                                  </>
                                )}
                              </button>
                            </div>
                          )
                        )}
                      </div>
                    </div>
                  ))}
                  {loading && (
                    <div className="flex gap-3 max-w-[80%] mr-auto">
                      <div className="w-7 h-7 rounded-full bg-primary text-white flex items-center justify-center animate-spin text-xs"><RefreshCw className="w-3.5 h-3.5" /></div>
                      <div className="p-3.5 rounded-lg text-xs bg-white border border-slate-200 text-slate-400 flex items-center gap-2">Executing query pipeline...</div>
                    </div>
                  )}
                </div>
                <form onSubmit={handleChatSubmit} className="p-4 border-t border-slate-200 bg-white flex gap-3 m-0 items-center">
                  <button 
                    type="button"
                    onClick={toggleVoiceListening}
                    className={`p-2.5 rounded-lg border transition-all cursor-pointer flex items-center justify-center shrink-0 ${
                      isListening 
                        ? "bg-red-50 border-red-200 text-red-500 animate-pulse shadow-sm" 
                        : "bg-slate-50 hover:bg-slate-100 border-slate-200 text-slate-500"
                    }`}
                    title={isListening ? "Stop listening" : "Ask by speaking"}
                  >
                    <Mic className="w-4 h-4" />
                  </button>
                  <input type="text" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Ask your data anything (e.g. 'Show revenue trend over time' or 'List datasets')..." className="flex-grow bg-slate-50 border border-slate-200 rounded-lg px-4 py-2.5 text-xs text-slate-800 focus:outline-none focus:border-secondary" />
                  <button type="submit" disabled={loading} className="btn-cyber p-2.5 rounded-lg flex items-center justify-center shrink-0"><Send className="w-4 h-4" /></button>
                </form>
              </div>
            )}

            {activeTab === "forecasting" && (
              <div className="space-y-6">
                <div className="cyber-card p-6 rounded-xl space-y-6">
                  <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
                    <div>
                      <label className="block text-[10px] uppercase font-bold text-slate-400 mb-1.5">Date Column</label>
                      <select value={dateColumn} onChange={(e) => setDateColumn(e.target.value)} className="w-full bg-slate-50 border border-slate-200 text-xs text-slate-700 px-3 py-2 rounded-md focus:outline-none focus:border-primary">
                        {schemaData?.columns?.map((c: any) => <option key={c.column} value={c.column}>{c.column} ({c.type})</option>)}
                      </select>
                    </div>
                    <div>
                      <label className="block text-[10px] uppercase font-bold text-slate-400 mb-1.5">Target Column</label>
                      <select value={targetColumn} onChange={(e) => setTargetColumn(e.target.value)} className="w-full bg-slate-50 border border-slate-200 text-xs text-slate-700 px-3 py-2 rounded-md focus:outline-none focus:border-primary">
                        {schemaData?.columns?.map((c: any) => <option key={c.column} value={c.column}>{c.column} ({c.type})</option>)}
                      </select>
                    </div>
                    <div>
                      <label className="block text-[10px] uppercase font-bold text-slate-400 mb-1.5">Horizon (periods)</label>
                      <input type="number" value={horizon} onChange={(e) => setHorizon(Number(e.target.value))} min={1} max={120} className="w-full bg-slate-50 border border-slate-200 text-xs text-slate-700 px-3 py-1.5 rounded-md focus:outline-none focus:border-primary" />
                    </div>
                    <div>
                      <label className="block text-[10px] uppercase font-bold text-slate-400 mb-1.5">Confidence Level</label>
                      <select value={confidenceLevel} onChange={(e) => setConfidenceLevel(Number(e.target.value))} className="w-full bg-slate-50 border border-slate-200 text-xs text-slate-700 px-3 py-2 rounded-md focus:outline-none focus:border-primary">
                        <option value="0.80">80% Interval</option>
                        <option value="0.90">90% Interval</option>
                        <option value="0.95">95% Interval</option>
                        <option value="0.99">99% Interval</option>
                      </select>
                    </div>
                    <div className="flex flex-col justify-end">
                      <label className="flex items-center gap-2 text-xs font-semibold text-slate-600 mb-2 cursor-pointer">
                        <input 
                          type="checkbox" 
                          checked={cleanOutliers} 
                          onChange={(e) => setCleanOutliers(e.target.checked)} 
                          className="rounded text-primary focus:ring-primary h-4 w-4 border-slate-300"
                        />
                        Clean Outliers (Z-score)
                      </label>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-4 gap-4 pt-4 border-t border-slate-100 items-end">
                    <div>
                      <label className="block text-[10px] uppercase font-bold text-slate-400 mb-1.5">Forecasting Model</label>
                      <select value={forecastingModel} onChange={(e) => setForecastingModel(e.target.value)} className="w-full bg-slate-50 border border-slate-200 text-xs text-slate-700 px-3 py-2 rounded-md focus:outline-none focus:border-primary">
                        <option value="auto">Auto Select (Validation R²)</option>
                        <option value="holt_winters">Holt-Winters Seasonality</option>
                        <option value="ar_lag">Autoregressive (AR) Lags</option>
                        <option value="linear">Linear Regression Trend</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-[10px] uppercase font-bold text-slate-400 mb-1.5">Seasonality Mode</label>
                      <select value={seasonalityMode} onChange={(e) => setSeasonalityMode(e.target.value)} className="w-full bg-slate-50 border border-slate-200 text-xs text-slate-700 px-3 py-2 rounded-md focus:outline-none focus:border-primary">
                        <option value="add">Additive Seasonality</option>
                        <option value="mul">Multiplicative Seasonality</option>
                        <option value="none">No Seasonality (Trend only)</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-[10px] uppercase font-bold text-slate-400 mb-1.5">Resampling Fill Method</label>
                      <select value={fillMethod} onChange={(e) => setFillMethod(e.target.value)} className="w-full bg-slate-50 border border-slate-200 text-xs text-slate-700 px-3 py-2 rounded-md focus:outline-none focus:border-primary">
                        <option value="interpolate">Linear Interpolation</option>
                        <option value="ffill">Forward Fill</option>
                        <option value="bfill">Backward Fill</option>
                        <option value="zero">Fill with Zero</option>
                      </select>
                    </div>
                    <button onClick={runForecasting} disabled={loading || !selectedDataset} className="btn-cyber py-2.5 rounded-md text-xs font-bold uppercase tracking-wider flex items-center justify-center gap-2">{loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />} Fit & Forecast</button>
                  </div>
                </div>

                {forecastResult ? (
                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    <div className="cyber-card p-6 rounded-xl space-y-4 lg:col-span-1">
                      <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider m-0">Model Quality Report</h3>
                      <div className="space-y-3">
                        <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                          <span className="text-[10px] text-slate-400 font-semibold block uppercase">Mean Absolute Error (MAE)</span>
                          <span className="text-xl font-bold text-slate-700">{forecastResult.metrics?.mae?.toFixed(4)}</span>
                        </div>
                        <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                          <span className="text-[10px] text-slate-400 font-semibold block uppercase">Root Mean Squared (RMSE)</span>
                          <span className="text-xl font-bold text-slate-700">{forecastResult.metrics?.rmse?.toFixed(4)}</span>
                        </div>
                        <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                          <span className="text-[10px] text-slate-400 font-semibold block uppercase">R-Squared (R²) Accuracy</span>
                          <span className="text-xl font-bold text-slate-700">{(forecastResult.metrics?.r2_score * 100)?.toFixed(2)}%</span>
                        </div>
                        <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                          <span className="text-[10px] text-slate-400 font-semibold block uppercase">Fitted Forecast Model</span>
                          <span className="text-xs font-bold text-slate-700 uppercase">{forecastResult.metrics?.selected_model?.replace("_", " ") || "AR Lag Model"}</span>
                        </div>
                      </div>
                    </div>

                    <div className="cyber-card p-6 rounded-xl lg:col-span-2 space-y-4">
                      <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider m-0">Seasonality Trend & Prediction bounds</h3>
                      <div className="h-80 w-full">
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={[...forecastResult.history.map((h: any) => ({ ...h, type: "history" })), ...forecastResult.forecast.map((f: any) => ({ ...f, type: "forecast" }))]}>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.05)" />
                            <XAxis dataKey="date" stroke="#64748b" tick={{ fontSize: 10 }} />
                            <YAxis stroke="#64748b" tick={{ fontSize: 10 }} />
                            <Tooltip contentStyle={{ backgroundColor: "#ffffff", borderColor: "#e2e8f0", color: "#0f172a" }} />
                            <Legend verticalAlign="top" height={36} />
                            <Area type="monotone" dataKey="upper_bound" stroke="transparent" fill="rgba(14, 165, 233, 0.08)" name="Upper Prediction Bound" />
                            <Area type="monotone" dataKey="lower_bound" stroke="transparent" fill="rgba(14, 165, 233, 0.08)" name="Lower Prediction Bound" />
                            <Line type="monotone" dataKey="value" stroke="#4F46E5" strokeWidth={2} dot={false} name="Historical Actual" />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="cyber-card p-8 rounded-xl text-center">
                    <LineIcon className="w-12 h-12 text-slate-200 mx-auto mb-3 animate-pulse" />
                    <p className="text-xs text-slate-400 m-0">Configure parameters above and click Train to generate model forecast.</p>
                  </div>
                )}
              </div>
            )}

            {activeTab === "audit" && (
              <div className="space-y-6">
                <div className="cyber-card p-6 rounded-xl space-y-4">
                  <div className="flex justify-between items-center border-b border-slate-100 pb-3">
                    <div className="flex items-center gap-2">
                      <Shield className="w-5 h-5 text-red-600 animate-pulse" />
                      <h4 className="text-xs font-black uppercase tracking-wider text-slate-800 m-0">
                        Immutable Compliance Audit Log
                      </h4>
                    </div>
                    <button 
                      onClick={fetchAuditLogs}
                      className="px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-[10px] font-bold text-slate-600 transition-all cursor-pointer flex items-center gap-1.5 shadow-sm"
                    >
                      <RefreshCw className="w-3.5 h-3.5" /> Refresh Audit Trail
                    </button>
                  </div>

                  <p className="text-xs text-slate-400 leading-relaxed m-0">
                    This ledger records all critical analytical operations, query executions, and dataset adjustments. Under enterprise compliance rules, these logs are guarded by database triggers raising execution exceptions on updates or deletes.
                  </p>

                  <div className="overflow-x-auto border border-slate-200 rounded-lg bg-white">
                    <table className="w-full text-left border-collapse text-[10px]">
                      <thead>
                        <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase tracking-wider sticky top-0">
                          <th className="p-3 font-semibold">Timestamp</th>
                          <th className="p-3 font-semibold">Event Type</th>
                          <th className="p-3 font-semibold">User Email</th>
                          <th className="p-3 font-semibold">IP Address</th>
                          <th className="p-3 font-semibold">Status</th>
                          <th className="p-3 font-semibold">Execution (ms)</th>
                          <th className="p-3 font-semibold">Confidence</th>
                          <th className="p-3 font-semibold">Dataset</th>
                          <th className="p-3 font-semibold">SQL Query</th>
                        </tr>
                      </thead>
                      <tbody>
                        {auditLogs.length === 0 ? (
                          <tr>
                            <td colSpan={9} className="p-4 text-center text-slate-400">
                              No compliance audit logs retrieved.
                            </td>
                          </tr>
                        ) : (
                          auditLogs.map((log, lIdx) => (
                            <tr key={log.event_id || lIdx} className="border-b border-slate-100 hover:bg-slate-50 text-slate-700">
                              <td className="p-3 font-mono">{log.created_at}</td>
                              <td className="p-3">
                                <span className={`px-2 py-0.5 rounded text-[8px] font-bold uppercase tracking-wide border ${
                                  log.event_type.includes("DELETE") ? "text-red-700 bg-red-50 border-red-200" :
                                  log.event_type.includes("UPLOAD") ? "text-emerald-700 bg-emerald-50 border-emerald-200" :
                                  "text-indigo-700 bg-indigo-50 border-indigo-200"
                                }`}>
                                  {log.event_type}
                                </span>
                              </td>
                              <td className="p-3 font-semibold">{log.user_email}</td>
                              <td className="p-3 font-mono">{log.ip_address}</td>
                              <td className="p-3">
                                <span className={`px-2 py-0.5 rounded text-[8px] font-bold uppercase tracking-wide border ${
                                  log.event_status === "SUCCESS" ? "text-emerald-700 bg-emerald-50 border-emerald-200" : "text-red-700 bg-red-50 border-red-200"
                                }`}>
                                  {log.event_status}
                                </span>
                              </td>
                              <td className="p-3 font-mono">{log.execution_time_ms ? `${log.execution_time_ms} ms` : "N/A"}</td>
                              <td className="p-3 font-mono font-bold">
                                {log.confidence_score !== null && log.confidence_score !== undefined ? `${Math.round(log.confidence_score * 100)}%` : "N/A"}
                              </td>
                              <td className="p-3 truncate max-w-[120px]" title={log.dataset_name}>{log.dataset_name || "N/A"}</td>
                              <td className="p-3 font-mono text-[9px] max-w-xs truncate" title={log.sql_executed}>{log.sql_executed || "N/A"}</td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}
          </div>
        </main>
        {correctionModalOpen && correctionReport && (
          <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white border border-slate-200 rounded-2xl max-w-lg w-full p-6 shadow-xl relative animate-in fade-in zoom-in-95 duration-200">
              <div className="flex items-center gap-2 mb-3">
                <AlertTriangle className="w-5 h-5 text-amber-500 animate-pulse" />
                <h3 className="text-sm font-black text-slate-800 uppercase tracking-wider m-0">
                  Resolve Column Ambiguities
                </h3>
              </div>
              
              <p className="text-xs text-slate-500 leading-relaxed mb-4">
                We detected potential mismatches in your natural language query columns. Check and adjust mappings to ensure correct query execution.
              </p>
              
              <div className="space-y-3 max-h-60 overflow-y-auto pr-2 mb-6">
                {correctionReport.column_mappings.map((mapping: any, idx: number) => (
                  <div key={idx} className="p-3 bg-slate-50 border border-slate-200 rounded-xl space-y-2.5">
                    <div className="flex justify-between text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                      <span>Query Token</span>
                      <span>Matched Column (Fuzzy Score)</span>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-mono text-xs text-slate-700 bg-slate-200/50 px-2 py-1 rounded font-bold border border-slate-200">
                        {mapping.query_token}
                      </span>
                      <span className="text-slate-400 font-bold">→</span>
                      <select
                        value={aliasCorrections[mapping.query_token] || mapping.matched_column}
                        onChange={(e) => {
                          const next = { ...aliasCorrections };
                          next[mapping.query_token] = e.target.value;
                          setAliasCorrections(next);
                        }}
                        className="bg-white border border-slate-200 text-xs font-semibold rounded-lg px-2 py-1.5 text-slate-700 focus:outline-none focus:border-primary flex-1 cursor-pointer"
                      >
                        {schemaData?.columns?.map((c: any) => (
                          <option key={c.column} value={c.column}>{c.column} ({c.type})</option>
                        ))}
                      </select>
                      <span className="text-[10px] font-mono font-bold text-slate-400">
                        ({Math.round(mapping.similarity * 100)}%)
                      </span>
                    </div>
                  </div>
                ))}
              </div>
              
              <div className="flex justify-end gap-3">
                <button 
                  onClick={() => setCorrectionModalOpen(false)}
                  className="px-4 py-2 border border-slate-200 text-slate-500 rounded-lg text-xs font-bold uppercase tracking-wider hover:bg-slate-50 cursor-pointer bg-transparent"
                >
                  Dismiss
                </button>
                <button 
                  onClick={async () => {
                    setCorrectionModalOpen(false);
                    setLoading(true);
                    try {
                      for (const token of Object.keys(aliasCorrections)) {
                        await fetch(`${API_URL}/api/schema/aliases`, {
                          method: "POST",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({
                            user_id: user?.id || "default_user",
                            dataset_name: correctingDataset,
                            query_token: token,
                            corrected_column: aliasCorrections[token]
                          })
                        });
                      }
                      await handleChatSubmit(undefined, lastQueryText);
                    } catch (e) {
                      console.error("Failed to save alias corrections:", e);
                      setLoading(false);
                    }
                  }}
                  className="btn-cyber px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider cursor-pointer"
                >
                  Apply Corrections & Re-run
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <>
      {currentView === "landing" && <LandingView />}
      {currentView === "login" && <LoginView />}
      {currentView === "register" && <RegisterView />}
      {currentView === "dashboard" && <DashboardView />}

      {activeModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-2xl max-w-lg w-full p-6 shadow-xl relative animate-in fade-in zoom-in-95 duration-200">
            <h3 className="text-sm font-black text-slate-800 uppercase tracking-wider mb-3">
              {activeModal === "privacy" && "Privacy Protocol Specification"}
              {activeModal === "terms" && "Workspace Terms of Use"}
              {activeModal === "api" && "Hyperlytics API Specifications"}
            </h3>
            <div className="text-xs text-slate-500 leading-relaxed max-h-60 overflow-y-auto mb-6 pr-2 space-y-3">
              {activeModal === "privacy" && (
                <>
                  <p><strong>1. Data Sandboxing:</strong> All ingested CSV, Parquet, and JSON datasets are processed purely in-memory using localized DuckDB analytical engines. Your dataset records never persist outside your active workspace sandboxed memory block.</p>
                  <p><strong>2. Google Auth isolation:</strong> Authentication claims are verified directly using official Google OAuth APIs, storing only name, email, and circular avatar URL metadata to enforce strict row-level security isolation on database tables.</p>
                  <p><strong>3. Key Security:</strong> Third-party LLM API keys (OpenAI, Anthropic, Gemini, Groq) are loaded temporarily in memory or retrieved from local storage headers, and are never logged or stored on the backend database.</p>
                </>
              )}
              {activeModal === "terms" && (
                <>
                  <p><strong>1. Analytical Provisioning:</strong> The Hyperlytics node is provided as an open-source Vite React + FastAPI template. Users are responsible for deploying and maintaining database instances and securing client credentials.</p>
                  <p><strong>2. In-Memory Computing:</strong> Large-scale data transformations, filtering, and forecast fit loops run client-side or on lightweight backend services. Ensure adequate system resources for large file volumes (e.g. Parquet structures over 500MB).</p>
                  <p><strong>3. Model Accuracy:</strong> Statistical projection models (Holt-Winters, AR Lags, Linear Trend) represent statistical estimators. Actual trends may deviate based on external factors not captured by historical sequences.</p>
                </>
              )}
              {activeModal === "api" && (
                <>
                  <p><strong>1. Ingestion Pipeline:</strong> <code>POST /api/upload</code> accepts multipart/form-data for file uploads, storing CSV, Parquet, and Excel sheets in the local workspace directory.</p>
                  <p><strong>2. Agent Supervisor:</strong> <code>POST /api/query</code> processes natural language questions using recursive agents, outputting structured JSON results containing generated SQL, datasets sample data, and predicted labels.</p>
                  <p><strong>3. SSE Stream Reader:</strong> <code>POST /api/query/stream</code> uses the Server-Sent Events (SSE) protocol to yield real-time token chunks and final dataset schemas.</p>
                  <p><strong>4. Row-Level Chat Isolation:</strong> <code>GET /api/chat?user_id=ID</code> loads chat logs isolated by user claims.</p>
                </>
              )}
            </div>
            <div className="flex justify-end">
              <button 
                onClick={() => setActiveModal(null)}
                className="btn-cyber px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider cursor-pointer"
              >
                Close Specification
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
