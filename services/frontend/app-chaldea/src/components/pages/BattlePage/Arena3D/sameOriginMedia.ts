// The public bucket sends no CORS headers, so WebGL can't sample its images.
// The api-gateway mirrors it read-only at /s3-media/fallofgods/ (see nginx.conf).
const BUCKET_PREFIX = "https://s3.eu-central-003.backblazeb2.com/fallofgods/";
const PROXY_PREFIX = "/s3-media/fallofgods/";

/** Same-origin URL for a bucket image, or null if the URL isn't from the bucket. */
export const toSameOriginMedia = (url: string | null | undefined): string | null =>
  url && url.startsWith(BUCKET_PREFIX) ? PROXY_PREFIX + url.slice(BUCKET_PREFIX.length) : null;
