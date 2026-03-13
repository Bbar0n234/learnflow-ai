import { buttonVariants } from "@/shared/ui/button";
import { Link } from "react-router";

export function WelcomePage() {
  return (
    <div className="flex h-full items-center justify-center">
      <div className="text-center">
        <h1 className="mb-4 text-4xl font-bold">LearnFlowAI</h1>
        <p className="mb-6 text-lg text-muted-foreground">
          Your AI-powered learning companion
        </p>
        <Link to="/projects/demo" className={buttonVariants()}>
          Open Demo Project
        </Link>
      </div>
    </div>
  );
}
