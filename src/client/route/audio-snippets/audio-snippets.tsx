import * as React from "react";
import {ErrorMessage} from "../../ui/error-message";
import {storage} from "../../storage";
import {useError} from "../../ui";
import {Link} from "react-router-dom";
import {bigIntLib} from "bigint-lib";
import {api} from "../../api";
import {Source} from "../../../api-mapper";

declare const SERVER_ROOT : string;
declare const API_ROOT : string;

function encodeAudioMeta (title : string, transcript : string) : string {
    const bytes = new TextEncoder().encode(
        JSON.stringify({ title, transcript })
    );
    let bin = "";
    for (let i = 0; i < bytes.length; ++i) {
        bin += String.fromCharCode(bytes[i]);
    }
    return btoa(bin);
}

export const AudioSnippetsPage = () => {
    const err = useError();
    const [nodeIdStr, setNodeIdStr] = React.useState("");
    const [title, setTitle] = React.useState("");
    const [transcript, setTranscript] = React.useState("");
    const [sources, setSources] = React.useState<Source[]>([]);
    const [loadingList, setLoadingList] = React.useState(false);
    const [saving, setSaving] = React.useState(false);

    const [recState, setRecState] = React.useState<"idle" | "recording" | "stopped">("idle");
    const mediaRecorderRef = React.useRef<MediaRecorder | null>(null);
    const chunksRef = React.useRef<Blob[]>([]);
    const [recordedBlob, setRecordedBlob] = React.useState<Blob | null>(null);
    const [previewUrl, setPreviewUrl] = React.useState<string | null>(null);

    const accessToken = storage.getAccessToken();

    React.useEffect(
        () => {
            return () => {
                if (previewUrl != null) {
                    URL.revokeObjectURL(previewUrl);
                }
            };
        },
        [previewUrl]
    );

    const refreshList = React.useCallback(() => {
        const id = nodeIdStr.trim();
        if (!/^\d+$/.test(id) || accessToken == undefined) {
            setSources([]);
            return;
        }
        setLoadingList(true);
        api.source.fetchByNode()
            .setParam({ nodeId : bigIntLib.BigInt(id) })
            .send()
            .then((r) => {
                const audioOnly = r.responseBody.filter((s) => s.sourceType === "audio");
                setSources(audioOnly);
                err.reset();
            })
            .catch((e) => {
                err.push("negative", [e.message]);
                setSources([]);
            })
            .then(() => {
                setLoadingList(false);
            });
    }, [nodeIdStr, accessToken, err]);

    const startRecording = async () => {
        err.reset();
        if (!navigator.mediaDevices || !window.MediaRecorder) {
            err.push("negative", ["Recording not supported in this browser. Use file upload instead."]);
            return;
        }
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio : true });
            chunksRef.current = [];
            const mr = new MediaRecorder(stream);
            mediaRecorderRef.current = mr;
            mr.ondataavailable = (ev : MediaRecorderDataAvailableEvent) => {
                if (ev.data.size > 0) {
                    chunksRef.current.push(ev.data);
                }
            };
            mr.onstop = () => {
                stream.getTracks().forEach((t) => t.stop());
                const blob = new Blob(chunksRef.current, { type : mr.mimeType || "audio/webm" });
                setRecordedBlob(blob);
                setPreviewUrl((old) => {
                    if (old != null) {
                        URL.revokeObjectURL(old);
                    }
                    return URL.createObjectURL(blob);
                });
                setRecState("stopped");
            };
            mr.start();
            setRecState("recording");
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            err.push("negative", [msg || "Microphone permission denied"]);
        }
    };

    const stopRecording = () => {
        const mr = mediaRecorderRef.current;
        if (mr != undefined && mr.state !== "inactive") {
            mr.stop();
        }
    };

    const onPickFile = (e : React.ChangeEvent<HTMLInputElement>) => {
        const f = e.target.files && e.target.files[0];
        if (f == undefined) {
            return;
        }
        setRecordedBlob(f);
        setPreviewUrl((old) => {
            if (old != null) {
                URL.revokeObjectURL(old);
            }
            return URL.createObjectURL(f);
        });
        setRecState("stopped");
        err.reset();
    };

    const uploadBlob = (blob : Blob) => {
        const id = nodeIdStr.trim();
        if (!/^\d+$/.test(id)) {
            err.push("negative", ["Enter a numeric node id."]);
            return;
        }
        if (accessToken == undefined) {
            err.push("negative", ["Set an access token first."]);
            return;
        }
        setSaving(true);
        err.reset();
        const url = `${SERVER_ROOT}${API_ROOT}/node/${id}/source/audio-snippet`;
        void fetch(
            url,
            {
                method : "POST",
                headers : {
                    "access-token" : accessToken,
                    "content-type" : blob.type || "application/octet-stream",
                    "x-audio-meta" : encodeAudioMeta(title.trim(), transcript),
                },
                body : blob,
            }
        )
            .then(async (res) => {
                if (!res.ok) {
                    const j = await res.json().catch(() => ({ errors : [] }));
                    const msg = (j.errors && j.errors[0] && j.errors[0].detail) || res.statusText;
                    throw new Error(msg);
                }
                setTitle("");
                setTranscript("");
                setRecordedBlob(null);
                setPreviewUrl((old) => {
                    if (old != null) {
                        URL.revokeObjectURL(old);
                    }
                    return null;
                });
                setRecState("idle");
                refreshList();
            })
            .catch((e : Error) => {
                err.push("negative", [e.message]);
            })
            .then(() => {
                setSaving(false);
            });
    };

    return (
        <div className="ui main container">
            <h2 className="ui header">Audio snippets (dataset)</h2>
            <p>
                Record or upload clips and attach them to a node as <code>sourceType: audio</code>.
                Use the transcript field for labels (e.g. ground-truth text for ASR/TTS datasets).
            </p>
            <p>
                <Link to="/node">Browse nodes</Link>
                {" · "}
                Open a node page to see all sources including audio.
            </p>

            <div className="ui segment">
                <h3>New snippet</h3>
                {
                    accessToken == undefined ?
                    <p className="ui warning message">Set an access token to save snippets.</p> :
                    undefined
                }
                <div className="ui form">
                    <div className="field">
                        <label>Node id</label>
                        <input
                            type="text"
                            value={nodeIdStr}
                            onChange={(e) => setNodeIdStr(e.target.value)}
                            placeholder="e.g. 42"
                        />
                    </div>
                    <div className="field">
                        <label>Title (optional)</label>
                        <input
                            type="text"
                            value={title}
                            onChange={(e) => setTitle(e.target.value)}
                            placeholder="Short label"
                        />
                    </div>
                    <div className="field">
                        <label>Transcript / notes (dataset label)</label>
                        <textarea
                            rows={4}
                            value={transcript}
                            onChange={(e) => setTranscript(e.target.value)}
                            placeholder="What is spoken in this clip (optional but useful for training data)"
                        />
                    </div>
                    <div className="fields">
                        <div className="field">
                            {
                                recState === "recording" ?
                                <button
                                    type="button"
                                    className="ui red button"
                                    onClick={stopRecording}
                                >
                                    Stop recording
                                </button> :
                                <button
                                    type="button"
                                    className="ui button"
                                    onClick={startRecording}
                                    disabled={accessToken == undefined}
                                >
                                    Record from microphone
                                </button>
                            }
                        </div>
                        <div className="field">
                            <label>Or upload a file</label>
                            <input
                                type="file"
                                accept="audio/*"
                                onChange={onPickFile}
                                disabled={accessToken == undefined}
                            />
                        </div>
                    </div>
                    {
                        previewUrl != undefined && previewUrl != null ?
                        <div className="field">
                            <label>Preview</label>
                            <audio controls src={previewUrl} style={{ width : "100%", maxWidth : "480px" }} />
                        </div> :
                        undefined
                    }
                    <button
                        type="button"
                        className="ui primary button"
                        disabled={
                            saving ||
                            accessToken == undefined ||
                            recordedBlob == undefined
                        }
                        onClick={() => {
                            if (recordedBlob != undefined) {
                                uploadBlob(recordedBlob);
                            }
                        }}
                    >
                        {saving ? "Saving…" : "Save to database"}
                    </button>
                </div>
                <ErrorMessage error={err}/>
            </div>

            <div className="ui segment">
                <h3>Audio sources on this node</h3>
                <button
                    type="button"
                    className="ui tiny button"
                    onClick={refreshList}
                    disabled={!/\d+/.test(nodeIdStr.trim())}
                >
                    Refresh list
                </button>
                <div className={loadingList ? "ui active loader" : ""} style={{ minHeight : "2rem" }}/>
                {
                    sources.length === 0 && !loadingList ?
                    <p><small>No audio sources for this node yet.</small></p> :
                    <div className="ui relaxed divided list">
                        {sources.map((s) => (
                            <div className="item" key={s.sourceId.toString()}>
                                <div className="content">
                                    <div className="header">
                                        {s.title.length === 0 ? "(untitled)" : s.title}
                                    </div>
                                    <div className="description">
                                        <small>
                                            {new Date(s.capturedAt).toLocaleString()}
                                        </small>
                                    </div>
                                    {
                                        s.filePath.length > 0 ?
                                        <audio
                                            controls
                                            src={`${SERVER_ROOT}/audio-snippets/${s.filePath}`}
                                            style={{ width : "100%", maxWidth : "420px", marginTop : "0.5rem" }}
                                        /> :
                                        undefined
                                    }
                                    {
                                        s.excerpt.length > 0 ?
                                        <p style={{ whiteSpace : "pre-wrap", marginTop : "0.5rem" }}>
                                            {s.excerpt}
                                        </p> :
                                        undefined
                                    }
                                </div>
                            </div>
                        ))}
                    </div>
                }
            </div>
        </div>
    );
};
