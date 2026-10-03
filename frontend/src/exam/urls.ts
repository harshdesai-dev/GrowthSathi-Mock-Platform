export function safeImage(url: string) {
  return /^https:\/\//i.test(url) ? url : undefined;
}
