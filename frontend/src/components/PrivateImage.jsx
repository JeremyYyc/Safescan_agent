import { useEffect, useState } from 'react';

// Business images are fetched with bearer auth; no token in URLs or public bucket.
export default function PrivateImage({ src, alt, ...props }) {
  const [image, setImage] = useState(null);
  useEffect(() => {
    if (!src) return;
    const controller = new AbortController();
    let objectUrl;
    const token = localStorage.getItem('safeScanAuthToken');
    fetch(src, { headers: token ? { Authorization: `Bearer ${token}` } : {}, signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error('Image unavailable'); return response.blob(); })
      .then(blob => { objectUrl = URL.createObjectURL(blob); setImage({ src, url: objectUrl }); })
      .catch(() => {});
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [src]);
  return image?.src === src ? <img src={image.url} alt={alt} {...props} /> : <span role="img" aria-label={alt}>Image loading…</span>;
}
