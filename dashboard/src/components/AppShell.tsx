"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Authenticator, useAuthenticator } from "@aws-amplify/ui-react";
import { Receipt, LayoutDashboard, LogOut } from "lucide-react";

const NAV_LINKS = [
  { href: "/invoices", label: "Invoices", icon: Receipt },
  { href: "/analytics", label: "Analytics", icon: LayoutDashboard },
];

function initialsFor(email?: string) {
  if (!email) return "?";
  return email[0].toUpperCase();
}

// The Cognito pool uses email as the username, so relabel the field
// everywhere it appears -- Amplify's default "Username" label is wrong here
// and confused the first login attempt.
const formFields = {
  signIn: {
    username: { label: "Email", placeholder: "you@company.com" },
  },
  forgotPassword: {
    username: { label: "Email", placeholder: "you@company.com" },
  },
};

// Self-signup is hidden: tenants are provisioned by an admin via
// `aws cognito-idp admin-create-user` with a `custom:tenant_id` attribute
// set. A self-registered account has no tenant_id and every API call would
// fail its tenant-isolation check, so offering "Create Account" here would
// just produce broken accounts.
function AuthHeader() {
  return (
    <div className="flex flex-col items-center gap-2 pb-2 pt-8">
      <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-600 text-lg font-semibold text-white">
        P
      </span>
      <h1 className="text-lg font-semibold text-gray-900">PayTrack Africa</h1>
      <p className="text-sm text-gray-500">Sign in to manage your invoices</p>
    </div>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <Authenticator
      hideSignUp
      formFields={formFields}
      components={{ Header: AuthHeader }}
    >
      {({ signOut, user }) => (
        <div className="min-h-screen bg-gray-50">
          <header className="sticky top-0 z-10 border-b border-gray-200 bg-white/80 backdrop-blur-sm">
            <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-3.5">
              <div className="flex items-center gap-8">
                <span className="flex items-center gap-2 font-semibold text-gray-900">
                  <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-600 text-sm text-white">
                    P
                  </span>
                  PayTrack Africa
                </span>
                <nav className="flex gap-1">
                  {NAV_LINKS.map(({ href, label, icon: Icon }) => {
                    const active = pathname?.startsWith(href);
                    return (
                      <Link
                        key={href}
                        href={href}
                        className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                          active
                            ? "bg-brand-50 text-brand-700"
                            : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                        }`}
                      >
                        <Icon size={16} />
                        {label}
                      </Link>
                    );
                  })}
                </nav>
              </div>
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2 text-sm text-gray-600">
                  <span className="flex h-7 w-7 items-center justify-center rounded-full bg-gray-200 text-xs font-medium text-gray-700">
                    {initialsFor(user?.signInDetails?.loginId)}
                  </span>
                  <span className="hidden sm:inline">{user?.signInDetails?.loginId}</span>
                </div>
                <button
                  onClick={signOut}
                  className="flex items-center gap-1.5 rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900"
                >
                  <LogOut size={14} />
                  Sign out
                </button>
              </div>
            </div>
          </header>
          <main className="mx-auto max-w-5xl px-6 py-8">{children}</main>
        </div>
      )}
    </Authenticator>
  );
}
