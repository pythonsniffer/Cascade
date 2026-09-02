import { useEffect } from "react";
import { Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { Config } from "./views/Config";
import { History } from "./views/History";
import { LiveTwin } from "./views/LiveTwin";
import { Pnl } from "./views/Pnl";
import { Quality } from "./views/Quality";
import { useTwin } from "./store/twin";

export default function App() {
  const { boot, connect, disconnect, bootError } = useTwin();

  useEffect(() => {
    void boot();
    connect();
    return () => disconnect();
  }, [boot, connect, disconnect]);

  if (bootError) {
    return (
      <div className="grid h-full place-items-center p-6">
        <div className="card max-w-md p-5 text-center">
          <h1 className="font-display text-[18px] font-medium">Can't reach the twin</h1>
          <p className="mt-2 text-[12.5px] leading-relaxed text-muted">
            The dashboard could not load its data from the backend. Check that the API is running,
            then reload.
          </p>
          <p className="mt-3 rounded-lg bg-black/[.03] px-3 py-2 font-mono text-[11px] text-muted">
            {bootError}
          </p>
          <button onClick={() => location.reload()}
                  className="mt-3 rounded-lg border border-hairline bg-white px-3 py-1.5
                             text-[12px] font-medium transition-colors hover:bg-black/[.03]">
            Reload
          </button>
        </div>
      </div>
    );
  }

  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<LiveTwin />} />
        <Route path="/quality" element={<Quality />} />
        <Route path="/pnl" element={<Pnl />} />
        <Route path="/history" element={<History />} />
        <Route path="/config" element={<Config />} />
        <Route path="*" element={<LiveTwin />} />
      </Routes>
    </AppShell>
  );
}
