"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Flame, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/components/providers/auth-provider";
import { ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function LoginPage() {
  const { login, register } = useAuth();
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (isSubmitting) return;
    setIsSubmitting(true);

    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password);
      }
      router.push("/");
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "Something went wrong.";
      toast.error(mode === "login" ? "Couldn't sign in" : "Couldn't create account", {
        description: message,
      });
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-[70vh] items-center justify-center">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: "easeOut" }}
        className="w-full max-w-sm"
      >
        <div className="mb-6 flex flex-col items-center gap-2 text-center">
          <span className="flex size-9 items-center justify-center rounded-lg bg-primary/15 text-primary">
            <Flame className="size-4.5" strokeWidth={2.25} />
          </span>
          <h1 className="text-lg font-semibold tracking-tight text-foreground">AgentForge</h1>
          <p className="text-sm text-muted-foreground">Sign in to build and watch your runs.</p>
        </div>

        <Card>
          <CardHeader>
            <Tabs value={mode} onValueChange={(value) => setMode(value as "login" | "register")}>
              <TabsList className="w-full">
                <TabsTrigger value="login">Sign in</TabsTrigger>
                <TabsTrigger value="register">Create account</TabsTrigger>
              </TabsList>
            </Tabs>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="flex flex-col gap-3">
              <div className="flex flex-col gap-1.5">
                <label htmlFor="email" className="text-xs font-medium text-muted-foreground">
                  Email
                </label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="password" className="text-xs font-medium text-muted-foreground">
                  Password
                </label>
                <Input
                  id="password"
                  type="password"
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  minLength={mode === "register" ? 8 : undefined}
                  required
                />
              </div>

              <Button type="submit" disabled={isSubmitting} className="mt-2 gap-1.5">
                {isSubmitting ? <Loader2 className="size-3.5 animate-spin" /> : null}
                {mode === "login" ? "Sign in" : "Create account"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  );
}
