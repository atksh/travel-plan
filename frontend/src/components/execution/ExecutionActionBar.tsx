"use client";

export function ExecutionActionBar({
  onArrive,
  onDepart,
  onSkip,
  onPreviewReplan,
  onAcceptReplan,
  hasPreview,
  disabled,
}: {
  onArrive: () => void;
  onDepart: () => void;
  onSkip: () => void;
  onPreviewReplan: () => void;
  onAcceptReplan: () => void;
  hasPreview: boolean;
  disabled: boolean;
}) {
  return (
    <div className="button-row">
      <button className="primary-button" type="button" disabled={disabled} onClick={onArrive}>
        到着
      </button>
      <button className="secondary-button" type="button" disabled={disabled} onClick={onDepart}>
        出発
      </button>
      <button className="secondary-button" type="button" disabled={disabled} onClick={onSkip}>
        スキップ
      </button>
      <button className="secondary-button" type="button" disabled={disabled} onClick={onPreviewReplan}>
        再計画プレビュー
      </button>
      <button className="primary-button" type="button" disabled={disabled || !hasPreview} onClick={onAcceptReplan}>
        再計画を採用
      </button>
    </div>
  );
}
