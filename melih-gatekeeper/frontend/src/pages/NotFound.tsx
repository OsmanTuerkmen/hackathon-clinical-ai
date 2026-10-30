import { Link } from "react-router-dom";
import { Page } from "@/components/Layout";
import { Button } from "@/components/ui";

export default function NotFound({ message }: { message?: string }) {
  return (
    <Page>
      <div className="mx-auto mt-16 max-w-md text-center">
        <div className="font-mono text-sm text-muted">404</div>
        <h1 className="mt-2 text-xl font-semibold">{message ?? "Page not found"}</h1>
        <Link to="/">
          <Button className="mt-6" variant="secondary">Back to start</Button>
        </Link>
      </div>
    </Page>
  );
}
