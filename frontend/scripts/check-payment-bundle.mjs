import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";

const forbidden = [
  "RAZORPAY_KEY_SECRET",
  "RAZORPAY_WEBHOOK_SECRET",
  process.env.RAZORPAY_KEY_SECRET,
  process.env.RAZORPAY_WEBHOOK_SECRET,
].filter(Boolean);

async function inspect(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) await inspect(path);
    else if (/\.(js|css|html|map|json)$/.test(entry.name)) {
      const content = await readFile(path, "utf8");
      if (forbidden.some((value) => content.includes(value))) {
        throw new Error(
          `Payment secret material detected in ${path}; do not deploy.`,
        );
      }
    }
  }
}

await inspect("dist");
console.log(
  "Production bundle contains no payment secret variable names or configured secret values.",
);
