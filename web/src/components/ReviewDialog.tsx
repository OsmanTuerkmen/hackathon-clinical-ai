import { InlineNotification, Modal, RadioButton, RadioButtonGroup, TextArea, TextInput } from "@carbon/react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Language } from "../api/types";
import { t } from "../i18n";

type ReviewAction = "release" | "hold" | "reject";

export function ReviewDialog({
  open,
  caseId,
  language,
  onClose,
  onSaved,
}: {
  open: boolean;
  caseId: string;
  language: Language;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [action, setAction] = useState<ReviewAction>("release");
  const [reason, setReason] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (open) {
      setAction("release");
      setReason("");
      setReviewer("");
      setAttempted(false);
      setError("");
    }
  }, [open]);

  const reasonValid = reason.trim().length >= 20;
  const reviewerValid = reviewer.trim().length >= 2;
  const submit = async () => {
    setAttempted(true);
    setError("");
    if (!reasonValid || !reviewerValid) return;
    setSaving(true);
    try {
      await api.review(caseId, { action, reason: reason.trim(), reviewer: reviewer.trim() });
      onClose();
      onSaved();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      modalHeading={t(language, "review.title")}
      primaryButtonText={t(language, "review.save")}
      secondaryButtonText={t(language, "review.cancel")}
      primaryButtonDisabled={saving}
      onRequestClose={onClose}
      onRequestSubmit={submit}
      onSecondarySubmit={onClose}
      size="sm"
    >
      <div className="review-form">
        {error && <InlineNotification kind="error" lowContrast title={error} />}
        <RadioButtonGroup
          name={`review-action-${caseId}`}
          legendText={t(language, "review.action")}
          valueSelected={action}
          onChange={(value) => setAction(value as ReviewAction)}
        >
          <RadioButton labelText={t(language, "review.release")} value="release" id="review-release" />
          <RadioButton labelText={t(language, "review.hold")} value="hold" id="review-hold" />
          <RadioButton labelText={t(language, "review.reject")} value="reject" id="review-reject" />
        </RadioButtonGroup>
        <TextArea
          id="review-reason"
          labelText={t(language, "review.reason")}
          helperText={t(language, "review.reasonHelp")}
          value={reason}
          maxLength={2000}
          invalid={attempted && !reasonValid}
          invalidText={t(language, "review.reasonShort")}
          onChange={(event) => setReason(event.currentTarget.value)}
        />
        <p className="review-form__counter" aria-live="polite">
          {reason.length} / 2000
        </p>
        <TextInput
          id="reviewer-name"
          labelText={t(language, "review.reviewer")}
          value={reviewer}
          invalid={attempted && !reviewerValid}
          invalidText={t(language, "review.reviewerRequired")}
          onChange={(event) => setReviewer(event.currentTarget.value)}
        />
      </div>
    </Modal>
  );
}
