import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import type { SearchResult } from "../src/api/types";
import { SubtitleMatchBoard } from "../src/components/SubtitleMatchBoard";

const VIDEO_RESULTS: SearchResult[] = [
  {
    subtitle_id: "video-1",
    track_type: "video_ref",
    raw_text: "我们到了这里",
    normalized_text: "我们到了这里",
    source_media_file_id: "video-file-1",
    source_start_ms: 1000,
    source_end_ms: 2500,
    flat_start_ms: 1000,
    flat_end_ms: 2500,
    relevance_score: 1,
    source_filename: "A001_C001.mov",
  },
];

const AUDIO_RESULTS: SearchResult[] = [
  {
    subtitle_id: "audio-1",
    track_type: "external_audio",
    raw_text: "我们到了这里",
    normalized_text: "我们到了这里",
    source_media_file_id: "audio-file-1",
    source_start_ms: 575180,
    source_end_ms: 576680,
    flat_start_ms: 575180,
    flat_end_ms: 576680,
    relevance_score: 1,
    source_filename: "ZOOM0001.wav",
  },
];

function TestHarness({ onAlign }: { onAlign: () => void }) {
  const [selectedVideo, setSelectedVideo] = useState<string | null>(null);
  const [selectedAudio, setSelectedAudio] = useState<string | null>(null);

  return (
    <SubtitleMatchBoard
      videoResults={VIDEO_RESULTS}
      audioResults={AUDIO_RESULTS}
      selectedVideoSubtitleId={selectedVideo}
      selectedAudioSubtitleId={selectedAudio}
      isAligning={false}
      lastOffsetMs={574180}
      onSelectVideo={setSelectedVideo}
      onSelectAudio={setSelectedAudio}
      onAlign={onAlign}
    />
  );
}

describe("SubtitleMatchBoard", () => {
  it("支持左右选择锚点并触发一键对齐", async () => {
    const user = userEvent.setup();
    const onAlign = vi.fn();
    render(<TestHarness onAlign={onAlign} />);

    await user.click(screen.getAllByRole("button", { name: /我们到了这里/i })[0]);
    await user.click(screen.getAllByRole("button", { name: /我们到了这里/i })[1]);
    await user.click(screen.getByRole("button", { name: "整轨一键对齐" }));

    expect(onAlign).toHaveBeenCalledTimes(1);
    expect(screen.getByText("最近 offset: 574180 ms")).toBeInTheDocument();
  });
});
