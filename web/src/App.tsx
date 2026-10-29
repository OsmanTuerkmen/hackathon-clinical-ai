import { Theme } from "@carbon/react";
import { useEffect, useMemo, useState } from "react";
import { api } from "./api/client";
import type { Identity, Language } from "./api/types";
import { Shell } from "./components/Shell";
import { t } from "./i18n";
import { ApplicantCasePage, ApplicantCasesPage, F2PlaceholderPage } from "./pages/apply/ApplicantPages";
import { CasePage } from "./pages/staff/CasePage";
import { InboxPage } from "./pages/staff/InboxPage";
import { LetterPage } from "./pages/letter/LetterPage";
import { RegisterPage } from "./pages/public/RegisterPage";
import { AppStateProvider, type Role, type ThemeName } from "./state/AppContext";

function readTheme(): ThemeName {
  const saved = localStorage.getItem("accessdesk.theme");
  if (saved === "white" || saved === "g100") return saved;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "g100" : "white";
}

function currentRoute(): string {
  return window.location.hash.slice(1) || "/staff/inbox";
}

function roleFor(route: string): Role {
  if (route.startsWith("/apply/")) return "applicant";
  if (route.startsWith("/register")) return "public";
  return "staff";
}

export default function App() {
  const [route, setRoute] = useState(currentRoute);
  const [language, setLanguage] = useState<Language>(() =>
    localStorage.getItem("accessdesk.language") === "en" ? "en" : "de",
  );
  const [theme, setTheme] = useState<ThemeName>(readTheme);
  const [identities, setIdentities] = useState<Identity[]>([]);
  const [identity, setIdentity] = useState(localStorage.getItem("accessdesk.identity") ?? "");
  const [ai, setAi] = useState<{ enabled: boolean; reason?: string; model?: string }>({
    enabled: false,
    reason: "AI not configured",
  });
  const role = useMemo(() => roleFor(route), [route]);

  useEffect(() => {
    const onHashChange = () => setRoute(currentRoute());
    window.addEventListener("hashchange", onHashChange);
    if (!window.location.hash) window.location.hash = "#/staff/inbox";
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    localStorage.setItem("accessdesk.language", language);
    document.documentElement.lang = language;
  }, [language]);

  useEffect(() => {
    localStorage.setItem("accessdesk.theme", theme);
  }, [theme]);

  useEffect(() => {
    localStorage.setItem("accessdesk.identity", identity);
  }, [identity]);

  useEffect(() => {
    let active = true;
    Promise.all([api.identities(), api.info()])
      .then(([identityList, info]) => {
        if (!active) return;
        setIdentities(identityList);
        setIdentity((current) =>
          identityList.some((item) => item.name === current)
            ? current
            : identityList[0]?.name ?? "",
        );
        setAi(info.ai);
      })
      .catch(() => {
        if (active) setAi({ enabled: false, reason: "AI not configured" });
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    requestAnimationFrame(() => {
      window.scrollTo(0, 0);
      document.getElementById("page-title")?.focus({ preventScroll: true });
    });
  }, [route]);

  const navigate = (path: string) => {
    const normalized = path.startsWith("/") ? path : `/${path}`;
    if (window.location.hash === `#${normalized}`) {
      setRoute(normalized);
      return;
    }
    window.location.hash = `#${normalized}`;
  };

  const state = {
    language,
    setLanguage,
    theme,
    setTheme,
    role,
    identity,
    setIdentity,
    identities,
    ai,
    route,
    navigate,
  };

  return (
    <Theme theme={theme}>
      <AppStateProvider value={state}>
        <Shell>
          <RouteView route={route} />
        </Shell>
      </AppStateProvider>
    </Theme>
  );
}

function RouteView({ route }: { route: string }) {
  if (route === "/staff/inbox" || route === "/") return <InboxPage />;
  if (route.startsWith("/staff/case/")) return <CasePage caseId={route.split("/")[3] ?? ""} />;
  if (route === "/apply/cases") return <ApplicantCasesPage />;
  if (route.startsWith("/apply/case/")) {
    return <ApplicantCasePage caseId={route.split("/")[3] ?? ""} />;
  }
  if (route.startsWith("/letter/")) return <LetterPage caseId={route.split("/")[2] ?? ""} />;
  if (route === "/register") return <RegisterPage />;
  if (
    route === "/apply/new"
    || route.startsWith("/apply/spe/")
    || route === "/staff/exports"
    || route === "/staff/audit"
    || route === "/staff/eval"
  ) {
    return <F2PlaceholderPage route={route} />;
  }
  return <InboxPage />;
}
