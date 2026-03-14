import { useState, useRef, useCallback } from "react";
import { getApiBase } from "@/lib/api";

export interface Attachment {
  path: string;
  name: string;
}

/**
 * Manages file attachments: local file selection, upload, paste, and removal.
 * Returns state + handlers for the Console input area.
 */
export function useAttachments(insertAtCursor: (text: string) => void) {
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const fileUploadRef = useRef<HTMLInputElement>(null);

  const addAttachment = useCallback((path: string, name: string) => {
    setAttachments(prev => {
      if (prev.some(a => a.path === path)) return prev;
      return [...prev, { path, name }];
    });
    insertAtCursor(`@${name} `);
  }, [insertAtCursor]);

  const removeAttachment = useCallback((idx: number) => {
    setAttachments(prev => {
      const att = prev[idx];
      if (att) {
        // Caller should also clean input text — we return the name for that
      }
      return prev.filter((_, i) => i !== idx);
    });
  }, []);

  const clearAttachments = useCallback(() => {
    setAttachments([]);
  }, []);

  // Handle file upload from native file picker (network/mobile clients)
  const handleFileUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const formData = new FormData();
      formData.append('file', file, file.name);
      try {
        const res = await fetch(`${getApiBase()}/api/fs/upload`, {
          method: 'POST', body: formData,
        });
        if (res.ok) {
          const data = await res.json();
          if (data.path) {
            const fname = data.filename || file.name;
            addAttachment(data.path, fname);
          }
        }
      } catch (err) {
        console.error('Failed to upload file:', err);
      }
    }
    if (fileUploadRef.current) fileUploadRef.current.value = '';
  }, [addAttachment]);

  // Handle paste — support pasting images
  const handlePaste = useCallback(async (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.type.startsWith('image/')) {
        e.preventDefault();
        const blob = item.getAsFile();
        if (!blob) continue;
        const formData = new FormData();
        const fname = `paste_${Date.now()}.png`;
        formData.append('file', blob, fname);
        try {
          const res = await fetch(`${getApiBase()}/api/fs/upload`, {
            method: 'POST', body: formData,
          });
          if (res.ok) {
            const data = await res.json();
            if (data.path) {
              const pastedName = data.filename || fname;
              addAttachment(data.path, pastedName);
            }
          }
        } catch (err) {
          console.error('Failed to upload pasted image:', err);
        }
        return;
      }
    }
  }, [addAttachment]);

  return {
    attachments,
    setAttachments,
    fileUploadRef,
    addAttachment,
    removeAttachment,
    clearAttachments,
    handleFileUpload,
    handlePaste,
  };
}
