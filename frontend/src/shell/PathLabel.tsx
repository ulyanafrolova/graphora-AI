import { splitPath } from "@/graph/names";

/** A file path as its name over its folder, each cut with an ellipsis when it does not fit. */
export function PathLabel({ path }: { path: string }) {
  const { name, dir } = splitPath(path);
  return (
    <>
      <span className="path-name">{name}</span>
      {dir && <span className="path-dir">{dir}</span>}
    </>
  );
}
