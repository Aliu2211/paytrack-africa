"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Authenticator } from "@aws-amplify/ui-react";
import { Receipt, LayoutDashboard, LogOut } from "lucide-react";

const NAV_LINKS = [
  { href: "/invoices", label: "Invoices", icon: Receipt },
  { href: "/analytics", label: "Analytics", icon: LayoutDashboard },
];

function initialsFor(email?: string) {
  if (!email) return "?";
  return email[0].toUpperCase();
}

const formFields = {
  signIn: {
    username: { label: "Email", placeholder: "you@company.com" },
  },
  forgotPassword: {
    username: { label: "Email", placeholder: "you@company.com" },
  },
};

function AuthHeader() {
  return (
    <div className="flex flex-col items-center gap-3 pb-2 pt-10">
      <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 text-2xl font-semibold text-white shadow-lg shadow-brand-600/20">
        P
      </span>
      <h1 className="text-xl font-semibold text-gray-900">PayTrack Africa</h1>
      <p className="text-sm text-gray-500">Sign in to manage your invoices</p>
    </div>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <Authenticator hideSignUp formFields={formFields} components={{ Header: AuthHeader }}>
      {({ signOut, user }) => (
        <div className="flex min-h-screen bg-gradient-to-br from-gray-50 via-white to-brand-50/40">
          <aside className="flex w-64 shrink-0 flex-col border-r border-gray-200 bg-white">
            <div className="flex items-center gap-2.5 px-6 py-6">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 text-base font-semibold text-white shadow-md shadow-brand-600/25">
                P
              </span>
              <span className="text-base font-semibold tracking-tight text-gray-900">PayTrack Africa</span>
            </div>

            <nav className="flex flex-col gap-1 px-3 pt-2">
              {NAV_LINKS.map(({ href, label, icon: Icon }) => {
                const active = pathname?.startsWith(href);
                return (
                  <Link
                    key={href}
                    href={href}
                    className={`group relative flex items-center gap-3 rounded-lg px-3.5 py-2.5 text-sm font-medium transition-colors ${
                      active ? "bg-brand-50 text-brand-700" : "text-gray-500 hover:bg-gray-50 hover:text-gray-900"
                    }`}
                  >
                    {active && (
                      <span className="absolute -left-3 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-brand-600" />
                    )}
                    <Icon size={17} className={active ? "text-brand-600" : "text-gray-400 group-hover:text-gray-500"} />
                    {label}
                  </Link>
                );
              })}
            </nav>

            <div className="mt-auto border-t border-gray-100 p-4">
              <div className="flex items-center gap-2.5 rounded-lg p-2">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-gray-200 to-gray-300 text-xs font-semibold text-gray-700">
                  {initialsFor(user?.signInDetails?.loginId)}
                </span>
                <span className="min-w-0 flex-1 truncate text-xs text-gray-600">
                  {user?.signInDetails?.loginId}
                </span>
                <button
                  onClick={signOut}
                  title="Sign out"
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-700"
                >
                  <LogOut size={14} />
                </button>
              </div>
            </div>
          </aside>

          <main className="flex-1 overflow-x-hidden px-10 py-10">
            <div className="mx-auto max-w-5xl">{children}</div>
          </main>
        </div>
      )}
    </Authenticator>
  );
}
