import { MotionConfig } from "framer-motion";
import { useEffect, useState } from "react";
import { Route, Routes, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import { Layout } from "@/components/Layout";
import { TooltipProvider } from "@/components/ui";
import { PersonaContext, type Persona } from "@/hooks";
import Apply from "@/pages/Apply";
import ApplyStatus from "@/pages/ApplyStatus";
import Landing from "@/pages/Landing";
import Metrics from "@/pages/Metrics";
import NotFound from "@/pages/NotFound";
import SpeWorkspacePage from "@/pages/SpeWorkspace";
import StaffDetail from "@/pages/StaffDetail";
import StaffQueue from "@/pages/StaffQueue";

function PersonaSync({ setPersona }: { setPersona: (p: Persona) => void }) {
  const loc = useLocation();
  useEffect(() => {
    if (loc.pathname.startsWith("/apply")) setPersona("applicant");
    else if (loc.pathname.startsWith("/staff") || loc.pathname.startsWith("/metrics")) setPersona("staff");
    window.scrollTo({ top: 0 });
  }, [loc.pathname, setPersona]);
  return null;
}

export default function App() {
  const [persona, setPersona] = useState<Persona>("staff");
  return (
    <MotionConfig reducedMotion="user">
      <PersonaContext.Provider value={{ persona, setPersona }}>
        <TooltipProvider>
          <PersonaSync setPersona={setPersona} />
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<Landing />} />
              <Route path="apply" element={<Apply />} />
              <Route path="apply/:id" element={<ApplyStatus />} />
              <Route path="staff" element={<StaffQueue />} />
              <Route path="staff/requests/:id" element={<StaffDetail />} />
              <Route path="spe/:workspaceId" element={<SpeWorkspacePage />} />
              <Route path="metrics" element={<Metrics />} />
              <Route path="*" element={<NotFound />} />
            </Route>
          </Routes>
          <Toaster position="bottom-right" offset={56} toastOptions={{ style: { fontFamily: '"Inter Tight", system-ui', borderRadius: 10 } }} />
        </TooltipProvider>
      </PersonaContext.Provider>
    </MotionConfig>
  );
}
