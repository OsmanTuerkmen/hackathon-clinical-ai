import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, Clock, RefreshCw } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { OutcomeBadges, PendingBadge } from "@/components/decision";
import { DecisionLetter } from "@/components/DecisionLetter";
import { Page } from "@/components/Layout";
import { PipelineStepper } from "@/components/PipelineStepper";
import { Button, Card, Skeleton } from "@/components/ui";
import { useDisplaySteps, useRequest } from "@/hooks";
import { fmtMs, fmtTime, shortOrg } from "@/lib/utils";
import NotFound from "./NotFound";

export default function ApplyStatus() {
  const { id } = useParams();
  const { data, error, isLoading, refetch } = useRequest(id);
  const { steps, finished } = useDisplaySteps(data?.steps);
  const decided = !!data?.decision && finished;

  if (error && (error as { status?: number }).status === 404) return <NotFound message={`No request ${id}`} />;

  return (
    <Page className="max-w-[980px]">
      <Link to="/apply" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <ArrowLeft size={14} /> New request
      </Link>
      <Card className="mb-6 px-6 pb-5 pt-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="text-sm text-muted">
              Request <span className="font-mono text-ink">{id}</span>
              {data && <> · submitted {fmtTime(data.submitted ?? data.request.submitted)}</>}
            </div>
            <div className="mt-0.5 truncate text-lg font-semibold tracking-tight">
              {data ? `${data.request.applicant.name} · ${shortOrg(data.request.applicant.organisation)}` : <Skeleton className="h-6 w-80" />}
            </div>
          </div>
          <div className="flex items-center gap-3">
            {decided && data?.decision ? (
              <OutcomeBadges outcome={data.decision.outcome} needsReview={data.decision.needs_review} downgradedFrom={data.decision.downgraded_from} reveal />
            ) : (
              <PendingBadge label={data?.status === "error" ? "Error" : "Under review"} />
            )}
            <span className="inline-flex items-center gap-1 font-mono text-sm tabular text-muted">
              <Clock size={13} /> {fmtMs(data?.elapsed_ms)}
            </span>
          </div>
        </div>
        <div className="mt-6">
          <PipelineStepper steps={steps} outcome={decided ? data?.decision?.outcome : null} />
        </div>
      </Card>

      {error && !data && (
        <Card className="p-6 text-center">
          <p className="text-reject">Could not load the request: {(error as Error).message}</p>
          <Button variant="secondary" className="mt-3" onClick={() => refetch()}>
            <RefreshCw size={14} /> Retry
          </Button>
        </Card>
      )}

      <AnimatePresence mode="wait">
        {decided && data ? (
          <DecisionLetter key="letter" detail={data} />
        ) : (
          (isLoading || data) && (
            <motion.div key="wait" exit={{ opacity: 0 }}>
              <Card className="p-10">
                <div className="mx-auto max-w-lg text-center">
                  <div className="font-serif text-lg">Your request is being reviewed.</div>
                  <p className="mt-2 text-muted">This usually takes less than 30 seconds. You can keep this page open; the decision letter appears here.</p>
                </div>
                <div className="mx-auto mt-8 max-w-xl space-y-3">
                  <Skeleton className="h-4 w-1/3" />
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-5/6" />
                  <Skeleton className="h-4 w-2/3" />
                </div>
              </Card>
            </motion.div>
          )
        )}
      </AnimatePresence>
    </Page>
  );
}
