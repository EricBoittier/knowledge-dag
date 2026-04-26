declare const BigInt : (x : string|number) => bigint;

/** Minimal typing for recording in browsers that support MediaRecorder */
interface MediaRecorderDataAvailableEvent {
    readonly data : Blob;
}
declare class MediaRecorder {
    public constructor (stream : MediaStream, options? : any);
    public readonly state : string;
    public readonly mimeType : string;
    public ondataavailable : ((ev : MediaRecorderDataAvailableEvent) => void) | null;
    public onstop : (() => void) | null;
    public start () : void;
    public stop () : void;
}
interface Window {
    MediaRecorder : typeof MediaRecorder;
}
