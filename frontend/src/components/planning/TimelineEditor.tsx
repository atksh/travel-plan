"use client";

import { DndContext, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { SortableContext, arrayMove, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { formatDuration, formatMinute } from "@/lib/format";
import type { Candidate, SolvePayload } from "@/lib/types";

function SortableStop({
  id,
  label,
  meta,
}: {
  id: number;
  label: string;
  meta: string;
}) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id });
  return (
    <article
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className="timeline-stop"
      {...attributes}
      {...listeners}
    >
      <div className="timeline-title">{label}</div>
      <div className="timeline-meta">{meta}</div>
    </article>
  );
}

export function TimelineEditor({
  candidates,
  orderedPlaceIds,
  solve,
  onReorder,
}: {
  candidates: Candidate[];
  orderedPlaceIds: number[];
  solve: SolvePayload | null;
  onReorder: (placeIds: number[]) => void;
}) {
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));
  const candidateMap = new Map(candidates.map((candidate) => [candidate.place_id, candidate]));

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) {
      return;
    }
    const oldIndex = orderedPlaceIds.indexOf(Number(active.id));
    const newIndex = orderedPlaceIds.indexOf(Number(over.id));
    if (oldIndex < 0 || newIndex < 0) {
      return;
    }
    onReorder(arrayMove(orderedPlaceIds, oldIndex, newIndex));
  }

  return (
    <section className="panel">
      <div className="section-heading">
        <h2>タイムライン</h2>
        <p>ドラッグ&ドロップで訪問順を並べ替えるとプレビューが更新されます。</p>
      </div>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={orderedPlaceIds} strategy={verticalListSortingStrategy}>
          <div className="stack">
            {orderedPlaceIds.length === 0 ? (
              <div className="empty-card">候補を追加するとここに並びます。</div>
            ) : (
              orderedPlaceIds.map((placeId) => {
                const candidate = candidateMap.get(placeId);
                const stop = solve?.stops.find((item) => item.place_id === placeId);
                return (
                  <SortableStop
                    key={placeId}
                    id={placeId}
                    label={candidate?.place.name ?? `Place ${placeId}`}
                    meta={
                      stop
                        ? `${formatMinute(stop.arrival_min)} - ${formatMinute(stop.departure_min)} / 滞在 ${formatDuration(stop.stay_min)}`
                        : `${candidate?.priority ?? "normal"} priority`
                    }
                  />
                );
              })
            )}
          </div>
        </SortableContext>
      </DndContext>
    </section>
  );
}
