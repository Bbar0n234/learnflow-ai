import { Wordmark } from "@/shared/ui/Wordmark";
import { Illustration } from "@/shared/ui/Illustration";

export function WelcomePage() {
  return (
    <div className="flex h-full items-center justify-center">
      <div className="text-center">
        <h1 className="mb-4 text-4xl">
          <Wordmark />
        </h1>
        <p className="mb-8 text-lg text-muted-foreground">
          Your AI-powered learning companion
        </p>
        <Illustration
          scene="welcome-hero"
          alt="Welcome to LearnFlowAI"
          className="mx-auto max-w-[460px] w-full"
        />
      </div>
    </div>
  );
}
