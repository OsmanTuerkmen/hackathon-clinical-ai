import {
  createContext,
  useContext,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";
import type { Identity, Language } from "../api/types";

export type ThemeName = "white" | "g100";
export type Role = "staff" | "applicant" | "public";

export interface AppContextValue {
  language: Language;
  setLanguage: Dispatch<SetStateAction<Language>>;
  theme: ThemeName;
  setTheme: Dispatch<SetStateAction<ThemeName>>;
  role: Role;
  identity: string;
  setIdentity: Dispatch<SetStateAction<string>>;
  identities: Identity[];
  ai: { enabled: boolean; reason?: string; model?: string };
  route: string;
  navigate: (path: string) => void;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppStateProvider({
  value,
  children,
}: {
  value: AppContextValue;
  children: ReactNode;
}) {
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useAppState(): AppContextValue {
  const context = useContext(AppContext);
  if (!context) throw new Error("AppStateProvider is missing");
  return context;
}
