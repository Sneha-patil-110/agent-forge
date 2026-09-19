"use client";

import { useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Flame, LogOut, Menu } from "lucide-react";
import { useAuth } from "@/components/providers/auth-provider";
import { wakeBackend } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

const PUBLIC_ROUTES = new Set(["/login"]);

let hasWokenBackend = false;

const NAV_LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/mcp", label: "MCP Servers" },
  { href: "/reliability", label: "Reliability" },
];

function isActiveRoute(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { status, user, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const isPublicRoute = PUBLIC_ROUTES.has(pathname);

  useEffect(() => {
    if (status === "unauthenticated" && !isPublicRoute) {
      router.replace("/login");
    } else if (status === "authenticated" && isPublicRoute) {
      router.replace("/");
    }
  }, [status, isPublicRoute, router]);

  useEffect(() => {
    if (hasWokenBackend) return;
    hasWokenBackend = true;
    wakeBackend();
  }, []);

  const showContent = isPublicRoute || status === "authenticated";

  return (
    <div className="flex h-screen flex-col">
      <header className="sticky top-0 z-40 border-b border-border/60 bg-background/70 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
          <Link href="/" className="flex items-center gap-2">
            <span className="flex size-7 items-center justify-center rounded-md bg-primary/15 text-primary">
              <Flame className="size-4" strokeWidth={2.25} />
            </span>
            <span className="text-sm font-semibold tracking-tight text-foreground">
              AgentForge
            </span>
          </Link>
          {status === "authenticated" && (
            <>
              <nav aria-label="Main" className="hidden items-center gap-2 text-sm text-muted-foreground md:flex">
                {NAV_LINKS.map((link) => {
                  const active = isActiveRoute(pathname, link.href);

                  return (
                    <Link
                      key={link.href}
                      href={link.href}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "rounded-md px-3 py-1.5 transition-colors hover:bg-accent hover:text-foreground",
                        active && "bg-accent text-foreground",
                      )}
                    >
                      {link.label}
                    </Link>
                  );
                })}
                <span className="mx-1 hidden text-xs text-muted-foreground/60 lg:inline">
                  {user?.email}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="gap-1.5 text-muted-foreground hover:text-foreground"
                  onClick={() => {
                    logout();
                    router.replace("/login");
                  }}
                >
                  <LogOut className="size-3.5" />
                  Sign out
                </Button>
              </nav>

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className="md:hidden"
                    aria-label="Open navigation menu"
                  >
                    <Menu className="size-4.5" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-48">
                  {NAV_LINKS.map((link) => (
                    <DropdownMenuItem key={link.href} asChild>
                      <Link
                        href={link.href}
                        aria-current={isActiveRoute(pathname, link.href) ? "page" : undefined}
                      >
                        {link.label}
                      </Link>
                    </DropdownMenuItem>
                  ))}
                  <DropdownMenuSeparator />
                  {user?.email && (
                    <DropdownMenuItem disabled className="text-muted-foreground">
                      {user.email}
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuItem
                    variant="destructive"
                    onSelect={() => {
                      logout();
                      router.replace("/login");
                    }}
                  >
                    <LogOut className="size-3.5" />
                    Sign out
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </>
          )}
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 min-h-0 overflow-y-auto px-6 py-8 [scrollbar-gutter:stable]">
        {showContent ? children : null}
      </main>
    </div>
  );
}
