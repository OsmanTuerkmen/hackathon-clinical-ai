import {
  Asleep,
  ChartColumn,
  Document,
  Home,
  Locked,
  Notebook,
  Sun,
  UserMultiple,
} from "@carbon/icons-react";
import {
  Button,
  Content,
  Header,
  HeaderGlobalAction,
  HeaderGlobalBar,
  HeaderMenuButton,
  HeaderName,
  HeaderPanel,
  Select,
  SelectItem,
  SideNav,
  SideNavItems,
  SideNavLink,
} from "@carbon/react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useAppState, type Role } from "../state/AppContext";
import { aiProviderModel, t } from "../i18n";

interface NavItem {
  path: string;
  key: Parameters<typeof t>[1];
  icon: typeof Document;
}

const NAV: Record<Role, NavItem[]> = {
  staff: [
    { path: "/staff/inbox", key: "nav.inbox", icon: Document },
    { path: "/staff/exports", key: "nav.exports", icon: Document },
    { path: "/staff/audit", key: "nav.audit", icon: Notebook },
    { path: "/staff/eval", key: "nav.eval", icon: ChartColumn },
  ],
  applicant: [
    { path: "/apply/new", key: "nav.applyNew", icon: Document },
    { path: "/apply/cases", key: "nav.applyCases", icon: UserMultiple },
    { path: "/apply/spe", key: "nav.spe", icon: Locked },
  ],
  public: [
    { path: "/register", key: "nav.register", icon: Home },
  ],
};

export function Shell({ children }: { children: ReactNode }) {
  const { 
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
  } = useAppState();
  const [navOpen, setNavOpen] = useState(() =>
    window.matchMedia("(min-width: 1056px)").matches,
  );
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [desktop, setDesktop] = useState(() =>
    window.matchMedia("(min-width: 1056px)").matches,
  );
  const navItems = NAV[role];
  const activePath = useMemo(() => route, [route]);
  const aiLabel = ai.enabled
    ? `${t(language, "ai.on")} · ${aiProviderModel(ai)}`
    : t(language, "ai.off");

  useEffect(() => {
    setNavOpen(false);
    setSettingsOpen(false);
  }, [route]);

  useEffect(() => {
    const media = window.matchMedia("(min-width: 1056px)");
    const onChange = (event: MediaQueryListEvent) => setDesktop(event.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  const setRole = (nextRole: Role) => {
    if (nextRole === "staff") navigate("/staff/inbox");
    else if (nextRole === "applicant") navigate("/apply/cases");
    else navigate("/register");
  };

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">{t(language, "nav.skip")}</a>
      <Header aria-label={t(language, "brand.name")} className="app-chrome">
        <HeaderMenuButton
          aria-label={desktop ? t(language, "nav.inbox") : (language === "de" ? "Menü" : "Menu")}
          isActive={desktop ? navOpen : settingsOpen}
          onClick={() => desktop
            ? setNavOpen((open) => !open)
            : setSettingsOpen((open) => !open)}
          isCollapsible
        />
        <HeaderName href="#/staff/inbox" prefix="">
          {t(language, "brand.name")}
        </HeaderName>
        <span className="app-header__subtitle">{t(language, "brand.subtitle")}</span>
        <HeaderGlobalBar>
          <div className="app-header__controls app-header__controls--desktop">
            <Select
              id="role-switch"
              labelText={t(language, "role.staff")}
              hideLabel
              value={role}
              onChange={(event) => setRole(event.target.value as Role)}
              size="sm"
            >
              <SelectItem value="staff" text={t(language, "role.staff")} />
              <SelectItem value="applicant" text={t(language, "role.applicant")} />
              <SelectItem value="public" text={t(language, "role.public")} />
            </Select>
            {role === "applicant" && (
              <Select
                id="identity-switch"
                className="identity-picker"
                labelText={t(language, "applicant.selectIdentity")}
                hideLabel
                value={identity}
                onChange={(event) => setIdentity(event.target.value)}
                size="sm"
              >
                {identities.map((item) => (
                  <SelectItem key={item.name} value={item.name} text={item.name} />
                ))}
              </Select>
            )}
            <Button
              kind="ghost"
              size="sm"
              onClick={() => setLanguage((current) => current === "de" ? "en" : "de")}
              aria-label={`${t(language, "language.switch")}: ${language.toUpperCase()}`}
            >
              {language.toUpperCase()}
            </Button>
            <HeaderGlobalAction
              aria-label={t(language, "theme.switch")}
              tooltipAlignment="end"
              onClick={() => setTheme((current) => current === "white" ? "g100" : "white")}
            >
              {theme === "white" ? <Asleep aria-hidden="true" /> : <Sun aria-hidden="true" />}
            </HeaderGlobalAction>
            <span className="app-header__ai" aria-label={aiLabel}>
              {aiLabel}
            </span>
          </div>
        </HeaderGlobalBar>
        <HeaderPanel
          aria-label={language === "de" ? "Einstellungen" : "Settings"}
          expanded={settingsOpen}
          className="app-header__panel"
        >
          <div className="app-header__controls app-header__controls--panel">
            <Select id="role-switch-mobile" labelText={language === "de" ? "Rolle" : "Role"} value={role}
              onChange={(event) => setRole(event.target.value as Role)} size="sm">
              <SelectItem value="staff" text={t(language, "role.staff")} />
              <SelectItem value="applicant" text={t(language, "role.applicant")} />
              <SelectItem value="public" text={t(language, "role.public")} />
            </Select>
            {role === "applicant" && (
              <Select id="identity-switch-mobile" labelText={t(language, "applicant.selectIdentity")}
                value={identity} onChange={(event) => setIdentity(event.target.value)} size="sm">
                {identities.map((item) => <SelectItem key={item.name} value={item.name} text={item.name} />)}
              </Select>
            )}
            <Button kind="ghost" size="sm"
              onClick={() => setLanguage((current) => current === "de" ? "en" : "de")}
              aria-label={`${t(language, "language.switch")}: ${language.toUpperCase()}`}>
              {language.toUpperCase()}
            </Button>
            <Button kind="ghost" size="sm"
              onClick={() => setTheme((current) => current === "white" ? "g100" : "white")}>
              {t(language, "theme.switch")}
            </Button>
            <span className="app-header__ai">{aiLabel}</span>
            <nav className="mobile-header-nav" aria-label={t(language, "role.staff")}>
              {navItems.map((item) => (
                <Button
                  key={item.path}
                  kind="ghost"
                  size="sm"
                  onClick={() => {
                    navigate(item.path);
                    setSettingsOpen(false);
                  }}
                >
                  {t(language, item.key)}
                </Button>
              ))}
            </nav>
          </div>
        </HeaderPanel>
      </Header>

      <div className="app-shell__content">
        <SideNav
          aria-label={t(language, role === "staff" ? "role.staff" : role === "applicant" ? "role.applicant" : "role.public")}
          expanded={desktop || navOpen}
          isPersistent={desktop}
          className="app-side-nav app-chrome"
          onOverlayClick={() => setNavOpen(false)}
        >
          <SideNavItems>
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <SideNavLink
                  key={item.path}
                  href={`#${item.path}`}
                  isActive={activePath === item.path || activePath.startsWith(`${item.path}/`)}
                  renderIcon={Icon}
                  onClick={() => setNavOpen(false)}
                >
                  {t(language, item.key)}
                </SideNavLink>
              );
            })}
          </SideNavItems>
        </SideNav>
        <Content className="app-main" id="main-content" tabIndex={-1}>
          {children}
        </Content>
      </div>
    </div>
  );
}
