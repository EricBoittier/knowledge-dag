import * as React from "react";
import * as classnames from "classnames";
import {RouteComponentProps} from "react-router";
import {ErrorMessage} from "../../ui/error-message";
import {DetailedItem} from "./detailed-item";
import {storage} from "../../storage";
import {Link} from "react-router-dom";
import {useFetch} from "./use-fetch";
import {api} from "../../api";
import {bigIntLib} from "bigint-lib";
import {Source, SourceType} from "../../../api-mapper";
import {useError} from "../../ui";

declare const SERVER_ROOT : string;

export interface FetchProps extends RouteComponentProps<{ nodeId : string }> {

}

export const Fetch = (props : FetchProps) => {
    const {
        error,
        node,
    } = useFetch({
        nodeId : props.match.params.nodeId,
    });
    const sourceError = useError();
    const [sourcesLoading, setSourcesLoading] = React.useState(true);
    const [sources, setSources] = React.useState<Source[]>([]);
    const [sourceType, setSourceType] = React.useState<SourceType>("url");
    const [url, setUrl] = React.useState("");
    const [title, setTitle] = React.useState("");
    const [excerpt, setExcerpt] = React.useState("");
    const [filePath, setFilePath] = React.useState("");
    const [submitDisabled, setSubmitDisabled] = React.useState(false);

    const fetchSources = React.useCallback(() => {
        setSourcesLoading(true);
        api.source.fetchByNode()
            .setParam({
                nodeId : bigIntLib.BigInt(props.match.params.nodeId),
            })
            .send()
            .then((response) => {
                setSources(response.responseBody);
                sourceError.reset();
            })
            .catch((err) => {
                sourceError.push("negative", [err.message]);
                setSourcesLoading(false);
            })
            .then(() => {
                setSourcesLoading(false);
            });
    }, [props.match.params.nodeId]);

    React.useEffect(
        () => {
            fetchSources();
        },
        [fetchSources]
    );

    const accessToken = storage.getAccessToken();
    const urlRequired = sourceType != "note" && sourceType != "audio";

    return (
        <div className="ui main container">
            <div className={classnames({
                "ui loader" : true,
                "active" : node == undefined,
            })}></div>
            <ErrorMessage error={error}/>
            {
                node == undefined ?
                undefined :
                <DetailedItem
                    className=""
                    node={node}
                    renderViewGraphButton={true}
                    buttons={
                        storage.getAccessToken() == undefined ?
                        undefined :
                        <div
                            className={"ui simple dropdown item button"}
                        >
                            Actions
                            <i className="dropdown icon"></i>
                            <div className="menu">
                                <Link className="ui item" to={`/node/${node.nodeId}/update`}>
                                    Edit
                                </Link>
                                <Link className="ui item" to={`/node/${node.nodeId}/dependency/create`}>
                                    Create Dependency
                                </Link>
                                {
                                    (node.dependencies.length == 0 && node.dependents.length == 0) ?
                                    <Link className="ui item" to={`/node/${node.nodeId}/delete`}>Delete</Link> :
                                    undefined
                                }
                                <Link className="ui item" to={`/node/${node.nodeId}/textbook/build`}>
                                    Build Textbook
                                </Link>
                            </div>
                        </div>
                    }
                />
            }
            <div className="ui segment">
                <h3>Sources</h3>
                <div className={classnames({
                    "ui loader" : true,
                    "active" : sourcesLoading,
                })}></div>
                {
                    sources.length == 0 ?
                    <p><small>No sources yet</small></p> :
                    <div className="ui relaxed divided list">
                        {sources.map((source) => {
                            return (
                                <div className="item" key={source.sourceId.toString()}>
                                    <div className="content">
                                        <div className="header">
                                            {source.title.length == 0 ? "(untitled source)" : source.title}
                                        </div>
                                        <div className="description">
                                            <small>
                                                {source.sourceType.toUpperCase()} | captured {new Date(source.capturedAt).toLocaleString()}
                                            </small>
                                        </div>
                                        {
                                            source.url.length == 0 ?
                                            undefined :
                                            <div>
                                                <a href={source.url} target="_blank" rel="noopener noreferrer">{source.url}</a>
                                            </div>
                                        }
                                        {
                                            source.sourceType === "audio" && source.filePath.length > 0 ?
                                            <audio
                                                controls
                                                src={`${SERVER_ROOT}/audio-snippets/${source.filePath}`}
                                                style={{ width : "100%", maxWidth : "420px", display : "block", marginTop : "0.35rem" }}
                                            /> :
                                            (
                                                source.filePath.length == 0 ?
                                                undefined :
                                                <div><small>Path: {source.filePath}</small></div>
                                            )
                                        }
                                        {
                                            source.excerpt.length == 0 ?
                                            undefined :
                                            <p style={{whiteSpace : "pre-wrap"}}>{source.excerpt}</p>
                                        }
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                }
                {
                    accessToken == undefined ?
                    <p><small>Set an access token to add sources.</small></p> :
                    <form
                        className="ui form"
                        onSubmit={(e) => {
                            e.preventDefault();
                            if (submitDisabled) {
                                return;
                            }
                            if (urlRequired && url.trim().length == 0) {
                                sourceError.push("negative", ["URL is required for url/pdf/image sources"]);
                                return;
                            }
                            setSubmitDisabled(true);
                            api.source.create()
                                .setHeader({
                                    "access-token" : accessToken,
                                })
                                .setParam({
                                    nodeId : bigIntLib.BigInt(props.match.params.nodeId),
                                })
                                .setBody({
                                    sourceType,
                                    url : url.trim(),
                                    title : title.trim(),
                                    excerpt : excerpt.trim(),
                                    filePath : filePath.trim(),
                                })
                                .send()
                                .then(() => {
                                    setUrl("");
                                    setTitle("");
                                    setExcerpt("");
                                    setFilePath("");
                                    sourceError.reset();
                                    fetchSources();
                                })
                                .catch((err) => {
                                    sourceError.push("negative", [err.message]);
                                    setSubmitDisabled(false);
                                })
                                .then(() => {
                                    setSubmitDisabled(false);
                                });
                        }}
                    >
                        <div className="fields equal width">
                            <div className="field">
                                <label>Type</label>
                                <select
                                    value={sourceType}
                                    onChange={(e) => {
                                        setSourceType(e.target.value as SourceType);
                                    }}
                                >
                                    <option value="url">URL</option>
                                    <option value="pdf">PDF</option>
                                    <option value="image">Image</option>
                                    <option value="note">Note</option>
                                    <option value="audio">Audio</option>
                                </select>
                            </div>
                            <div className="field">
                                <label>Title</label>
                                <input
                                    type="text"
                                    value={title}
                                    onChange={(e) => {
                                        setTitle(e.target.value);
                                    }}
                                    placeholder="Optional title"
                                />
                            </div>
                        </div>
                        <div className="field">
                            <label>URL {urlRequired ? "(required)" : "(optional)"}</label>
                            <input
                                type="text"
                                value={url}
                                onChange={(e) => {
                                    setUrl(e.target.value);
                                }}
                                placeholder="https://example.com/..."
                            />
                        </div>
                        <div className="field">
                            <label>File Path (optional metadata)</label>
                            <input
                                type="text"
                                value={filePath}
                                onChange={(e) => {
                                    setFilePath(e.target.value);
                                }}
                                placeholder="/path/to/file.png"
                            />
                        </div>
                        <div className="field">
                            <label>Excerpt / Note</label>
                            <textarea
                                rows={3}
                                value={excerpt}
                                onChange={(e) => {
                                    setExcerpt(e.target.value);
                                }}
                                placeholder="Optional notes or quoted excerpt"
                            />
                        </div>
                        <button className="ui button primary" type="submit" disabled={submitDisabled}>
                            Add Source
                        </button>
                    </form>
                }
                <ErrorMessage error={sourceError}/>
            </div>
        </div>
    );
};
