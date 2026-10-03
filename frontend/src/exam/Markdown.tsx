import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { safeImage } from "./urls";

export function Markdown({ text }: { text: string }) {
  return (
    <div className="exam-markdown">
      <ReactMarkdown
        skipHtml
        remarkPlugins={[remarkMath]}
        rehypePlugins={[
          [
            rehypeKatex,
            { trust: false, strict: "error", maxExpand: 500, maxSize: 20 },
          ],
        ]}
        components={{
          img: ({ src, alt }) => (
            <img
              src={safeImage(typeof src === "string" ? src : "")}
              alt={alt ?? "Question diagram"}
              loading="lazy"
              referrerPolicy="no-referrer"
            />
          ),
          a: ({ children }) => <span>{children}</span>,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
