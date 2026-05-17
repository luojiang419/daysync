from __future__ import annotations

from difflib import SequenceMatcher
import json
import sqlite3
from statistics import median

from daysync_core.errors import DaySyncError
from daysync_core.utils import new_uuid, utc_now_iso

AUTO_PASS_MIN_CANDIDATE_MARGIN = 0.1


def create_manual_anchor_sync(
    connection: sqlite3.Connection,
    project_id: str,
    video_subtitle_id: str,
    audio_subtitle_id: str,
) -> dict[str, object]:
    video_anchor = _load_anchor(connection, project_id, video_subtitle_id, "video_ref")
    audio_anchor = _load_anchor(connection, project_id, audio_subtitle_id, "external_audio")
    if video_anchor["source_start_ms"] is None or audio_anchor["source_start_ms"] is None:
        raise DaySyncError(
            "ANCHOR_SUBTITLE_INVALID",
            "Selected subtitles do not have mapped source times",
        )

    offset_ms = audio_anchor["source_start_ms"] - video_anchor["source_start_ms"]
    video_media = _load_media(connection, video_anchor["source_media_file_id"])
    sync_id = new_uuid()
    now = utc_now_iso()
    sync_result = {
        "id": sync_id,
        "project_id": project_id,
        "session_id": None,
        "video_media_file_id": video_anchor["source_media_file_id"],
        "audio_media_file_id": audio_anchor["source_media_file_id"],
        "video_in_ms": 0,
        "video_out_ms": video_media["duration_ms"],
        "audio_in_ms": offset_ms,
        "audio_out_ms": offset_ms + video_media["duration_ms"],
        "offset_ms": offset_ms,
        "drift_ppm": None,
        "confidence_score": 1.0,
        "status": "accepted_manual",
        "source": "manual_anchor",
        "video_anchor_subtitle_id": video_subtitle_id,
        "audio_anchor_subtitle_id": audio_subtitle_id,
        "confidence_breakdown_json": json.dumps({"manual_anchor": True}),
        "created_at": now,
        "updated_at": now,
    }
    connection.execute(
        """
        INSERT INTO sync_results (
          id, project_id, session_id, video_media_file_id, audio_media_file_id, video_in_ms, video_out_ms,
          audio_in_ms, audio_out_ms, offset_ms, drift_ppm, confidence_score, status, source,
          video_anchor_subtitle_id, audio_anchor_subtitle_id, confidence_breakdown_json, created_at, updated_at
        )
        VALUES (:id, :project_id, :session_id, :video_media_file_id, :audio_media_file_id, :video_in_ms,
                :video_out_ms, :audio_in_ms, :audio_out_ms, :offset_ms, :drift_ppm, :confidence_score,
                :status, :source, :video_anchor_subtitle_id, :audio_anchor_subtitle_id,
                :confidence_breakdown_json, :created_at, :updated_at)
        """,
        sync_result,
    )
    connection.commit()
    return sync_result


def list_sync_results(connection: sqlite3.Connection, project_id: str) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT sr.id, sr.project_id, sr.video_media_file_id, sr.audio_media_file_id, sr.video_in_ms,
               sr.video_out_ms, sr.audio_in_ms, sr.audio_out_ms, sr.offset_ms, sr.confidence_score,
               sr.status, sr.source, sr.video_anchor_subtitle_id, sr.audio_anchor_subtitle_id,
               sr.confidence_breakdown_json, sr.created_at, sr.updated_at,
               vm.filename AS video_file, am.filename AS audio_file,
               vs.raw_text AS video_anchor_text, aus.raw_text AS audio_anchor_text
        FROM sync_results sr
        JOIN media_files vm ON vm.id = sr.video_media_file_id
        JOIN media_files am ON am.id = sr.audio_media_file_id
        LEFT JOIN subtitles vs ON vs.id = sr.video_anchor_subtitle_id
        LEFT JOIN subtitles aus ON aus.id = sr.audio_anchor_subtitle_id
        WHERE sr.project_id = ?
        ORDER BY sr.created_at DESC
        """,
        (project_id,),
    ).fetchall()
    if not rows:
        return []

    sync_result_ids = [row["id"] for row in rows]
    review_events = connection.execute(
        """
        SELECT id, sync_result_id, event_type, old_offset_ms, new_offset_ms, note, created_at
        FROM review_events
        WHERE sync_result_id IN ({placeholders})
        ORDER BY created_at DESC
        """.format(placeholders=",".join("?" for _ in sync_result_ids)),
        sync_result_ids,
    ).fetchall()
    review_events_by_result: dict[str, list[dict[str, object]]] = {}
    for event in review_events:
        review_events_by_result.setdefault(event["sync_result_id"], []).append(dict(event))

    results: list[dict[str, object]] = []
    for row in rows:
        item = dict(row)
        item["confidence_breakdown"] = _parse_json(item.pop("confidence_breakdown_json"))
        item["review_events"] = review_events_by_result.get(item["id"], [])
        results.append(item)
    return results


def list_review_queue(connection: sqlite3.Connection, project_id: str) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT sr.id, sr.project_id, sr.video_media_file_id, sr.audio_media_file_id, sr.video_in_ms,
               sr.video_out_ms, sr.audio_in_ms, sr.audio_out_ms, sr.offset_ms, sr.confidence_score,
               sr.status, sr.source, sr.video_anchor_subtitle_id, sr.audio_anchor_subtitle_id,
               sr.confidence_breakdown_json, sr.created_at, sr.updated_at,
               vm.filename AS video_file, am.filename AS audio_file,
               vs.raw_text AS video_anchor_text, aus.raw_text AS audio_anchor_text
        FROM sync_results sr
        JOIN media_files vm ON vm.id = sr.video_media_file_id
        JOIN media_files am ON am.id = sr.audio_media_file_id
        LEFT JOIN subtitles vs ON vs.id = sr.video_anchor_subtitle_id
        LEFT JOIN subtitles aus ON aus.id = sr.audio_anchor_subtitle_id
        WHERE sr.project_id = ?
          AND sr.status IN ('candidate', 'needs_review')
        ORDER BY sr.created_at DESC
        """,
        (project_id,),
    ).fetchall()

    if not rows:
        return []

    sync_result_ids = [row["id"] for row in rows]
    review_events = connection.execute(
        """
        SELECT id, sync_result_id, event_type, old_offset_ms, new_offset_ms, note, created_at
        FROM review_events
        WHERE sync_result_id IN ({placeholders})
        ORDER BY created_at DESC
        """.format(placeholders=",".join("?" for _ in sync_result_ids)),
        sync_result_ids,
    ).fetchall()
    review_events_by_result: dict[str, list[dict[str, object]]] = {}
    for event in review_events:
        review_events_by_result.setdefault(event["sync_result_id"], []).append(dict(event))

    queue_items: list[dict[str, object]] = []
    for row in rows:
        item = dict(row)
        item["confidence_breakdown"] = _parse_json(item.pop("confidence_breakdown_json"))
        item["review_events"] = review_events_by_result.get(item["id"], [])
        queue_items.append(item)
    return queue_items


def recommend_auto_candidates(
    connection: sqlite3.Connection,
    project_id: str,
    anchor_subtitle_id: str,
    limit: int = 5,
    context_radius: int = 1,
) -> dict[str, object]:
    recommendation = _recommend_auto_candidates_internal(
        connection,
        project_id,
        anchor_subtitle_id,
        context_radius=context_radius,
    )
    return {
        **recommendation,
        "limit": limit,
        "candidates": recommendation["candidates"][:limit],
    }


def create_cluster_sync_candidate(
    connection: sqlite3.Connection,
    project_id: str,
    pairs: list[dict[str, str]],
    tolerance_ms: int = 500,
    min_inlier_ratio: float = 0.6,
    min_anchor_count: int = 3,
    context_radius: int = 1,
    note: str | None = None,
) -> dict[str, object]:
    analysis = analyze_offset_cluster(
        connection,
        project_id,
        pairs,
        tolerance_ms=tolerance_ms,
        min_inlier_ratio=min_inlier_ratio,
        min_anchor_count=min_anchor_count,
        context_radius=context_radius,
    )
    pair_analyses = analysis["pair_analyses"]
    cluster_summary = analysis["cluster_summary"]
    if not pair_analyses:
        raise DaySyncError("ANCHOR_SUBTITLE_INVALID", "No cluster pairs available to create candidate")

    relevant_pairs = [pair for pair in pair_analyses if pair["is_inlier"]]
    if not relevant_pairs:
        relevant_pairs = pair_analyses

    video_media_ids = {pair["video_source_media_file_id"] for pair in relevant_pairs}
    audio_media_ids = {pair["audio_source_media_file_id"] for pair in relevant_pairs}
    if len(video_media_ids) != 1 or len(audio_media_ids) != 1:
        raise DaySyncError(
            "ANCHOR_SUBTITLE_INVALID",
            "Cluster candidate spans multiple media files and cannot be saved as one sync result",
        )

    video_media_id = next(iter(video_media_ids))
    audio_media_id = next(iter(audio_media_ids))
    representative_pair = min(
        relevant_pairs,
        key=lambda pair: (
            pair["cluster_deviation_ms"],
            0 if pair["reverse_match_consistent"] else 1,
            -pair["final_score"],
        ),
    )
    proposed_offset_ms = (
        cluster_summary["final_offset_ms"]
        if cluster_summary["final_offset_ms"] is not None
        else cluster_summary["median_offset_ms"]
    )
    video_media = _load_media(connection, video_media_id)

    reverse_match_consistency = (
        cluster_summary["reverse_consistent_count"] / cluster_summary["candidate_count"]
        if cluster_summary["candidate_count"]
        else 0.0
    )
    text_similarity = _average_metric(relevant_pairs, "text_similarity")
    context_similarity = _average_metric(relevant_pairs, "context_similarity")
    candidate_margin = _average_metric(relevant_pairs, "candidate_margin")
    offset_cluster_stability = cluster_summary["inlier_ratio"]
    negative_evidence_count = sum(pair["negative_evidence_count"] for pair in relevant_pairs)
    final_score = max(
        0.0,
        min(
            1.0,
            text_similarity * 0.3
            + context_similarity * 0.2
            + offset_cluster_stability * 0.2
            + reverse_match_consistency * 0.2
            + candidate_margin * 0.1
            - min(negative_evidence_count, 5) * 0.03,
        ),
    )
    confidence_breakdown = {
        "text_similarity": round(text_similarity, 4),
        "context_similarity": round(context_similarity, 4),
        "offset_cluster_stability": round(offset_cluster_stability, 4),
        "reverse_match_consistency": round(reverse_match_consistency, 4),
        "candidate_margin": round(candidate_margin, 4),
        "negative_evidence_count": negative_evidence_count,
        "final_score": round(final_score, 4),
        "cluster_summary": cluster_summary,
        "pair_analyses": pair_analyses,
        "note": note,
    }
    auto_accept_decision = _evaluate_auto_accept(
        cluster_summary=cluster_summary,
        relevant_pairs=relevant_pairs,
        average_candidate_margin=candidate_margin,
    )
    confidence_breakdown["auto_accept_decision"] = auto_accept_decision

    sync_result = {
        "id": new_uuid(),
        "project_id": project_id,
        "session_id": None,
        "video_media_file_id": video_media_id,
        "audio_media_file_id": audio_media_id,
        "video_in_ms": 0,
        "video_out_ms": video_media["duration_ms"],
        "audio_in_ms": proposed_offset_ms,
        "audio_out_ms": proposed_offset_ms + video_media["duration_ms"],
        "offset_ms": proposed_offset_ms,
        "drift_ppm": None,
        "confidence_score": round(final_score, 4),
        "status": "accepted_auto" if auto_accept_decision["eligible"] else "needs_review",
        "source": "auto_text",
        "video_anchor_subtitle_id": representative_pair["video_subtitle_id"],
        "audio_anchor_subtitle_id": representative_pair["audio_subtitle_id"],
        "confidence_breakdown_json": json.dumps(confidence_breakdown, ensure_ascii=False),
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
    }
    connection.execute(
        """
        INSERT INTO sync_results (
          id, project_id, session_id, video_media_file_id, audio_media_file_id, video_in_ms, video_out_ms,
          audio_in_ms, audio_out_ms, offset_ms, drift_ppm, confidence_score, status, source,
          video_anchor_subtitle_id, audio_anchor_subtitle_id, confidence_breakdown_json, created_at, updated_at
        )
        VALUES (:id, :project_id, :session_id, :video_media_file_id, :audio_media_file_id, :video_in_ms,
                :video_out_ms, :audio_in_ms, :audio_out_ms, :offset_ms, :drift_ppm, :confidence_score,
                :status, :source, :video_anchor_subtitle_id, :audio_anchor_subtitle_id,
                :confidence_breakdown_json, :created_at, :updated_at)
        """,
        sync_result,
    )
    connection.commit()
    return {
        "sync_result": sync_result,
        "cluster_summary": cluster_summary,
        "auto_accept_decision": auto_accept_decision,
    }


def review_sync_result(
    connection: sqlite3.Connection,
    project_id: str,
    sync_result_id: str,
    action: str,
    new_offset_ms: int | None = None,
    note: str | None = None,
) -> dict[str, object]:
    sync_result = _load_sync_result(connection, project_id, sync_result_id)
    old_offset_ms = sync_result["offset_ms"]
    updated_at = utc_now_iso()
    status = sync_result["status"]
    offset_ms = old_offset_ms
    audio_in_ms = sync_result["audio_in_ms"]
    audio_out_ms = sync_result["audio_out_ms"]
    review_event_type = action

    if action == "accepted":
        status = "accepted_auto"
    elif action == "rejected":
        status = "rejected"
    elif action == "adjusted":
        if new_offset_ms is None:
            raise DaySyncError("ANCHOR_SUBTITLE_INVALID", "new_offset_ms is required for adjusted review")
        status = "accepted_manual"
        offset_ms = new_offset_ms
        audio_in_ms = new_offset_ms
        audio_out_ms = new_offset_ms + sync_result["video_out_ms"]
    elif action == "commented":
        status = sync_result["status"]
    else:
        raise DaySyncError("ANCHOR_SUBTITLE_INVALID", f"Unsupported review action: {action}")

    connection.execute(
        """
        UPDATE sync_results
        SET status = ?, offset_ms = ?, audio_in_ms = ?, audio_out_ms = ?, updated_at = ?
        WHERE id = ? AND project_id = ?
        """,
        (status, offset_ms, audio_in_ms, audio_out_ms, updated_at, sync_result_id, project_id),
    )
    review_event = {
        "id": new_uuid(),
        "project_id": project_id,
        "sync_result_id": sync_result_id,
        "event_type": review_event_type,
        "old_offset_ms": old_offset_ms,
        "new_offset_ms": offset_ms if action in {"accepted", "adjusted"} else None,
        "note": note,
        "created_at": updated_at,
    }
    connection.execute(
        """
        INSERT INTO review_events (
          id, project_id, sync_result_id, event_type, old_offset_ms, new_offset_ms, note, created_at
        )
        VALUES (:id, :project_id, :sync_result_id, :event_type, :old_offset_ms, :new_offset_ms, :note, :created_at)
        """,
        review_event,
    )
    connection.commit()

    updated_result = connection.execute(
        """
        SELECT sr.id, sr.project_id, sr.video_media_file_id, sr.audio_media_file_id, sr.video_in_ms,
               sr.video_out_ms, sr.audio_in_ms, sr.audio_out_ms, sr.offset_ms, sr.confidence_score,
               sr.status, sr.source, sr.video_anchor_subtitle_id, sr.audio_anchor_subtitle_id,
               sr.confidence_breakdown_json, sr.created_at, sr.updated_at,
               vm.filename AS video_file, am.filename AS audio_file,
               vs.raw_text AS video_anchor_text, aus.raw_text AS audio_anchor_text
        FROM sync_results sr
        JOIN media_files vm ON vm.id = sr.video_media_file_id
        JOIN media_files am ON am.id = sr.audio_media_file_id
        LEFT JOIN subtitles vs ON vs.id = sr.video_anchor_subtitle_id
        LEFT JOIN subtitles aus ON aus.id = sr.audio_anchor_subtitle_id
        WHERE sr.id = ? AND sr.project_id = ?
        """,
        (sync_result_id, project_id),
    ).fetchone()
    review_events = connection.execute(
        """
        SELECT id, sync_result_id, event_type, old_offset_ms, new_offset_ms, note, created_at
        FROM review_events
        WHERE sync_result_id = ?
        ORDER BY created_at DESC
        """,
        (sync_result_id,),
    ).fetchall()
    result_payload = dict(updated_result)
    result_payload["confidence_breakdown"] = _parse_json(result_payload.pop("confidence_breakdown_json"))
    result_payload["review_events"] = [dict(event) for event in review_events]
    return {
        "sync_result": result_payload,
        "review_event": review_event,
    }


def analyze_offset_cluster(
    connection: sqlite3.Connection,
    project_id: str,
    pairs: list[dict[str, str]],
    tolerance_ms: int = 500,
    min_inlier_ratio: float = 0.6,
    min_anchor_count: int = 3,
    context_radius: int = 1,
) -> dict[str, object]:
    if not pairs:
        raise DaySyncError("ANCHOR_SUBTITLE_INVALID", "At least one subtitle pair is required")

    unique_pairs: list[dict[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for pair in pairs:
        pair_key = (pair["video_subtitle_id"], pair["audio_subtitle_id"])
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)
        unique_pairs.append(pair)

    pair_analyses: list[dict[str, object]] = []
    for pair in unique_pairs:
        recommendation = _recommend_auto_candidates_internal(
            connection,
            project_id,
            pair["video_subtitle_id"],
            context_radius=context_radius,
        )
        video_anchor = recommendation["anchor"]
        candidate = next(
            (
                item
                for item in recommendation["candidates"]
                if item["subtitle_id"] == pair["audio_subtitle_id"]
            ),
            None,
        )
        if candidate is None:
            raise DaySyncError(
                "ANCHOR_SUBTITLE_INVALID",
                "Selected audio subtitle is not available for cluster analysis",
                pair,
            )
        if video_anchor["source_start_ms"] is None or candidate["source_start_ms"] is None:
            raise DaySyncError(
                "ANCHOR_SUBTITLE_INVALID",
                "Selected subtitle pair does not have mapped source times",
                pair,
            )

        offset_ms = candidate["source_start_ms"] - video_anchor["source_start_ms"]
        pair_negative_evidence_count = candidate["negative_evidence_count"]
        if video_anchor["mapping_status"] != "ok":
            pair_negative_evidence_count += 1
        if video_anchor["duplicate_count"] > 1:
            pair_negative_evidence_count += 1

        pair_analyses.append(
            {
                "video_subtitle_id": video_anchor["subtitle_id"],
                "video_text": video_anchor["raw_text"],
                "video_source_media_file_id": video_anchor["source_media_file_id"],
                "video_source_filename": video_anchor["source_filename"],
                "video_source_start_ms": video_anchor["source_start_ms"],
                "audio_subtitle_id": candidate["subtitle_id"],
                "audio_text": candidate["raw_text"],
                "audio_source_media_file_id": candidate["source_media_file_id"],
                "audio_source_filename": candidate["source_filename"],
                "audio_source_start_ms": candidate["source_start_ms"],
                "offset_ms": offset_ms,
                "text_similarity": candidate["text_similarity"],
                "context_similarity": candidate["context_similarity"],
                "final_score": candidate["final_score"],
                "candidate_margin": candidate["candidate_margin"],
                "reverse_margin": candidate["reverse_margin"],
                "reverse_match_consistent": candidate["reverse_match_consistent"],
                "negative_evidence_count": pair_negative_evidence_count,
                "mapping_warning": candidate["mapping_warning"] or video_anchor["mapping_warning"],
                "reverse_top_subtitle_id": candidate["reverse_top_subtitle_id"],
                "reverse_top_raw_text": candidate["reverse_top_raw_text"],
            }
        )

    offset_values = [analysis["offset_ms"] for analysis in pair_analyses]
    median_offset_ms = int(round(median(offset_values)))
    inlier_offsets: list[int] = []
    for analysis in pair_analyses:
        cluster_deviation_ms = abs(analysis["offset_ms"] - median_offset_ms)
        is_inlier = cluster_deviation_ms <= tolerance_ms
        analysis["cluster_deviation_ms"] = cluster_deviation_ms
        analysis["is_inlier"] = is_inlier
        if is_inlier:
            inlier_offsets.append(analysis["offset_ms"])

    inlier_count = len(inlier_offsets)
    candidate_count = len(pair_analyses)
    inlier_ratio = inlier_count / candidate_count if candidate_count else 0.0
    passes = candidate_count >= min_anchor_count and inlier_ratio >= min_inlier_ratio and inlier_count > 0
    final_offset_ms = int(round(median(inlier_offsets))) if passes else None

    reasons: list[str] = []
    if candidate_count < min_anchor_count:
        reasons.append("not_enough_anchor_pairs")
    if inlier_ratio < min_inlier_ratio:
        reasons.append("inlier_ratio_below_threshold")
    if any(not analysis["reverse_match_consistent"] for analysis in pair_analyses):
        reasons.append("reverse_match_inconsistency_present")
    if any(analysis["negative_evidence_count"] > 0 for analysis in pair_analyses):
        reasons.append("negative_evidence_present")

    relevant_pairs = [pair for pair in pair_analyses if pair["is_inlier"]]
    if not relevant_pairs:
        relevant_pairs = pair_analyses
    auto_accept_decision = _evaluate_auto_accept(
        cluster_summary={
            "passes": passes,
            "inlier_count": inlier_count,
            "min_anchor_count": min_anchor_count,
        },
        relevant_pairs=relevant_pairs,
        average_candidate_margin=_average_metric(relevant_pairs, "candidate_margin"),
    )

    return {
        "pair_analyses": pair_analyses,
        "cluster_summary": {
            "candidate_count": candidate_count,
            "median_offset_ms": median_offset_ms,
            "final_offset_ms": final_offset_ms,
            "inlier_count": inlier_count,
            "inlier_ratio": round(inlier_ratio, 4),
            "passes": passes,
            "tolerance_ms": tolerance_ms,
            "min_inlier_ratio": min_inlier_ratio,
            "min_anchor_count": min_anchor_count,
            "reverse_consistent_count": sum(
                1 for analysis in pair_analyses if analysis["reverse_match_consistent"]
            ),
            "negative_evidence_pair_count": sum(
                1 for analysis in pair_analyses if analysis["negative_evidence_count"] > 0
            ),
            "reasons": reasons,
        },
        "auto_accept_decision": auto_accept_decision,
    }


def _recommend_auto_candidates_internal(
    connection: sqlite3.Connection,
    project_id: str,
    anchor_subtitle_id: str,
    *,
    context_radius: int,
) -> dict[str, object]:
    anchor = _load_project_subtitle(connection, project_id, anchor_subtitle_id)
    target_track_type = "external_audio" if anchor["track_type"] == "video_ref" else "video_ref"
    anchor_track_rows = _load_track_subtitles(connection, anchor["track_id"])
    target_rows = _load_project_subtitles_by_track_type(connection, project_id, target_track_type)
    target_duplicates = _count_normalized_duplicates(target_rows)
    grouped_target_rows = _group_rows_by_track(target_rows)
    anchor_duplicates = _count_normalized_duplicates(anchor_track_rows)

    anchor_context = _build_context_payload(anchor_track_rows, anchor["id"], context_radius)
    ordered_candidates = _score_target_candidates(
        anchor=anchor,
        anchor_context=anchor_context,
        target_rows=target_rows,
        grouped_target_rows=grouped_target_rows,
        target_duplicates=target_duplicates,
        context_radius=context_radius,
    )
    _apply_candidate_margins(ordered_candidates)

    grouped_anchor_rows = {anchor["track_id"]: anchor_track_rows}
    for candidate in ordered_candidates:
        candidate_row = next(row for row in target_rows if row["id"] == candidate["subtitle_id"])
        candidate_track_rows = grouped_target_rows[candidate_row["track_id"]]
        candidate_context = _build_context_payload(candidate_track_rows, candidate_row["id"], context_radius)
        reverse_candidates = _score_target_candidates(
            anchor=candidate_row,
            anchor_context=candidate_context,
            target_rows=anchor_track_rows,
            grouped_target_rows=grouped_anchor_rows,
            target_duplicates=anchor_duplicates,
            context_radius=context_radius,
        )
        _apply_candidate_margins(reverse_candidates)
        reverse_top_candidate = reverse_candidates[0] if reverse_candidates else None
        candidate["reverse_match_consistent"] = (
            reverse_top_candidate is not None and reverse_top_candidate["subtitle_id"] == anchor["id"]
        )
        candidate["reverse_top_subtitle_id"] = (
            reverse_top_candidate["subtitle_id"] if reverse_top_candidate else None
        )
        candidate["reverse_top_raw_text"] = (
            reverse_top_candidate["raw_text"] if reverse_top_candidate else None
        )
        candidate["reverse_margin"] = (
            reverse_top_candidate["candidate_margin"] if reverse_top_candidate else 0.0
        )

    return {
        "anchor": {
            "subtitle_id": anchor["id"],
            "track_type": anchor["track_type"],
            "track_id": anchor["track_id"],
            "raw_text": anchor["raw_text"],
            "normalized_text": anchor["normalized_text"],
            "source_media_file_id": anchor["source_media_file_id"],
            "source_filename": anchor["source_filename"],
            "source_start_ms": anchor["source_start_ms"],
            "source_end_ms": anchor["source_end_ms"],
            "flat_start_ms": anchor["flat_start_ms"],
            "flat_end_ms": anchor["flat_end_ms"],
            "mapping_status": anchor["mapping_status"],
            "mapping_warning": anchor["mapping_warning"],
            "context_before_text": anchor_context["context_before_text"],
            "context_after_text": anchor_context["context_after_text"],
            "context_window_text": anchor_context["context_window_text"],
            "duplicate_count": anchor_duplicates.get(anchor["normalized_text"], 0),
        },
        "target_track_type": target_track_type,
        "context_radius": context_radius,
        "candidates": ordered_candidates,
    }


def _load_anchor(
    connection: sqlite3.Connection, project_id: str, subtitle_id: str, expected_track_type: str
) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT s.id, s.source_media_file_id, s.source_start_ms, s.source_end_ms, st.track_type
        FROM subtitles s
        JOIN subtitle_tracks st ON st.id = s.track_id
        WHERE s.id = ? AND st.project_id = ?
        """,
        (subtitle_id, project_id),
    ).fetchone()
    if row is None or row["track_type"] != expected_track_type or row["source_media_file_id"] is None:
        raise DaySyncError("ANCHOR_SUBTITLE_INVALID", "Selected anchor subtitle is invalid")
    return row


def _load_media(connection: sqlite3.Connection, media_file_id: str) -> sqlite3.Row:
    row = connection.execute(
        "SELECT id, duration_ms FROM media_files WHERE id = ?",
        (media_file_id,),
    ).fetchone()
    if row is None:
        raise DaySyncError("MEDIA_FILE_NOT_FOUND", "Media file not found for sync result")
    return row


def _load_project_subtitle(connection: sqlite3.Connection, project_id: str, subtitle_id: str) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT s.id, s.track_id, s.subtitle_index, s.flat_start_ms, s.flat_end_ms,
               s.source_media_file_id, s.source_start_ms, s.source_end_ms,
               s.raw_text, s.normalized_text, s.mapping_status, s.mapping_warning,
               st.track_type, mf.filename AS source_filename
        FROM subtitles s
        JOIN subtitle_tracks st ON st.id = s.track_id
        LEFT JOIN media_files mf ON mf.id = s.source_media_file_id
        WHERE st.project_id = ? AND s.id = ?
        """,
        (project_id, subtitle_id),
    ).fetchone()
    if row is None:
        raise DaySyncError("ANCHOR_SUBTITLE_INVALID", "Selected anchor subtitle is invalid")
    return row


def _load_track_subtitles(connection: sqlite3.Connection, track_id: str) -> list[sqlite3.Row]:
    rows = connection.execute(
        """
        SELECT s.id, s.track_id, s.subtitle_index, s.flat_start_ms, s.flat_end_ms,
               s.source_media_file_id, s.source_start_ms, s.source_end_ms,
               s.raw_text, s.normalized_text, s.mapping_status, s.mapping_warning,
               st.track_type, mf.filename AS source_filename
        FROM subtitles s
        JOIN subtitle_tracks st ON st.id = s.track_id
        LEFT JOIN media_files mf ON mf.id = s.source_media_file_id
        WHERE s.track_id = ?
        ORDER BY s.subtitle_index
        """,
        (track_id,),
    ).fetchall()
    return list(rows)


def _load_project_subtitles_by_track_type(
    connection: sqlite3.Connection, project_id: str, track_type: str
) -> list[sqlite3.Row]:
    rows = connection.execute(
        """
        SELECT s.id, s.track_id, s.subtitle_index, s.flat_start_ms, s.flat_end_ms,
               s.source_media_file_id, s.source_start_ms, s.source_end_ms,
               s.raw_text, s.normalized_text, s.mapping_status, s.mapping_warning,
               st.track_type, mf.filename AS source_filename
        FROM subtitles s
        JOIN subtitle_tracks st ON st.id = s.track_id
        LEFT JOIN media_files mf ON mf.id = s.source_media_file_id
        WHERE st.project_id = ? AND st.track_type = ?
        ORDER BY st.id, s.subtitle_index
        """,
        (project_id, track_type),
    ).fetchall()
    return list(rows)


def _group_rows_by_track(rows: list[sqlite3.Row]) -> dict[str, list[sqlite3.Row]]:
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault(row["track_id"], []).append(row)
    return grouped


def _count_normalized_duplicates(rows: list[sqlite3.Row]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        normalized_text = row["normalized_text"]
        counts[normalized_text] = counts.get(normalized_text, 0) + 1
    return counts


def _build_context_payload(
    rows: list[sqlite3.Row], subtitle_id: str, context_radius: int
) -> dict[str, str]:
    index = next((item_index for item_index, item in enumerate(rows) if item["id"] == subtitle_id), None)
    if index is None:
        return {
            "context_before_text": "",
            "context_after_text": "",
            "context_window_text": "",
        }

    before_items = rows[max(0, index - context_radius) : index]
    after_items = rows[index + 1 : index + 1 + context_radius]
    context_before_text = " ".join(item["raw_text"] for item in before_items).strip()
    context_after_text = " ".join(item["raw_text"] for item in after_items).strip()
    normalized_before = " ".join(item["normalized_text"] for item in before_items).strip()
    normalized_after = " ".join(item["normalized_text"] for item in after_items).strip()
    current_normalized = rows[index]["normalized_text"]
    context_window_text = " | ".join(
        part for part in [normalized_before, current_normalized, normalized_after] if part
    ).strip()
    return {
        "context_before_text": context_before_text,
        "context_after_text": context_after_text,
        "context_window_text": context_window_text,
    }


def _score_target_candidates(
    *,
    anchor: sqlite3.Row,
    anchor_context: dict[str, str],
    target_rows: list[sqlite3.Row],
    grouped_target_rows: dict[str, list[sqlite3.Row]],
    target_duplicates: dict[str, int],
    context_radius: int,
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for row in target_rows:
        candidate_context = _build_context_payload(grouped_target_rows[row["track_id"]], row["id"], context_radius)
        negative_evidence_count = 0
        if row["mapping_status"] != "ok":
            negative_evidence_count += 1
        if target_duplicates.get(row["normalized_text"], 0) > 1:
            negative_evidence_count += 1

        text_similarity = _similarity(anchor["normalized_text"], row["normalized_text"])
        context_similarity = _similarity(
            anchor_context["context_window_text"],
            candidate_context["context_window_text"],
        )
        exact_match_bonus = 0.05 if anchor["normalized_text"] == row["normalized_text"] else 0.0
        final_score = max(
            0.0,
            min(
                1.0,
                text_similarity * 0.7
                + context_similarity * 0.25
                + exact_match_bonus
                - negative_evidence_count * 0.05,
            ),
        )
        candidates.append(
            {
                "subtitle_id": row["id"],
                "track_type": row["track_type"],
                "track_id": row["track_id"],
                "raw_text": row["raw_text"],
                "normalized_text": row["normalized_text"],
                "source_media_file_id": row["source_media_file_id"],
                "source_filename": row["source_filename"],
                "source_start_ms": row["source_start_ms"],
                "source_end_ms": row["source_end_ms"],
                "flat_start_ms": row["flat_start_ms"],
                "flat_end_ms": row["flat_end_ms"],
                "mapping_status": row["mapping_status"],
                "mapping_warning": row["mapping_warning"],
                "text_similarity": round(text_similarity, 4),
                "context_similarity": round(context_similarity, 4),
                "final_score": round(final_score, 4),
                "negative_evidence_count": negative_evidence_count,
                "duplicate_count": target_duplicates.get(row["normalized_text"], 0),
                "context_before_text": candidate_context["context_before_text"],
                "context_after_text": candidate_context["context_after_text"],
                "context_window_text": candidate_context["context_window_text"],
            }
        )
    return sorted(
        candidates,
        key=lambda item: (-item["final_score"], -item["text_similarity"], item["flat_start_ms"]),
    )


def _apply_candidate_margins(candidates: list[dict[str, object]]) -> None:
    for index, candidate in enumerate(candidates):
        next_score = candidates[index + 1]["final_score"] if index + 1 < len(candidates) else 0.0
        candidate["candidate_margin"] = round(candidate["final_score"] - next_score, 4)


def _similarity(left: str | None, right: str | None) -> float:
    left_text = (left or "").strip()
    right_text = (right or "").strip()
    if not left_text and not right_text:
        return 1.0
    if not left_text or not right_text:
        return 0.0
    return SequenceMatcher(None, left_text, right_text).ratio()


def _load_sync_result(connection: sqlite3.Connection, project_id: str, sync_result_id: str) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT id, project_id, video_media_file_id, audio_media_file_id, video_in_ms, video_out_ms,
               audio_in_ms, audio_out_ms, offset_ms, status, source
        FROM sync_results
        WHERE id = ? AND project_id = ?
        """,
        (sync_result_id, project_id),
    ).fetchone()
    if row is None:
        raise DaySyncError("SYNC_RESULT_NOT_FOUND", "Sync result not found")
    return row


def _average_metric(items: list[dict[str, object]], key: str) -> float:
    if not items:
        return 0.0
    return sum(float(item[key]) for item in items) / len(items)


def _evaluate_auto_accept(
    *,
    cluster_summary: dict[str, object],
    relevant_pairs: list[dict[str, object]],
    average_candidate_margin: float,
) -> dict[str, object]:
    reasons: list[str] = []
    if not bool(cluster_summary["passes"]):
        reasons.append("cluster_not_stable_enough")
    if int(cluster_summary["inlier_count"]) < int(cluster_summary["min_anchor_count"]):
        reasons.append("not_enough_inlier_anchors")
    if any(not pair["reverse_match_consistent"] for pair in relevant_pairs):
        reasons.append("reverse_match_not_consistent")
    if average_candidate_margin < AUTO_PASS_MIN_CANDIDATE_MARGIN:
        reasons.append("candidate_margin_too_small")
    if any(pair["negative_evidence_count"] > 0 for pair in relevant_pairs):
        reasons.append("negative_evidence_present")

    return {
        "eligible": not reasons,
        "reasons": reasons,
        "average_candidate_margin": round(average_candidate_margin, 4),
        "min_candidate_margin": AUTO_PASS_MIN_CANDIDATE_MARGIN,
    }


def _parse_json(value: str | None) -> dict[str, object]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
