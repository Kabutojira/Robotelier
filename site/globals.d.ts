export declare global {
  interface Document {
    addEventListener<K extends keyof CustomEventMap>(
      type: K,
      listener: (this: Document, event: CustomEventMap[K]) => void,
    ): void;
    removeEventListener<K extends keyof CustomEventMap>(
      type: K,
      listener: (this: Document, event: CustomEventMap[K]) => void,
    ): void;
    dispatchEvent<K extends keyof CustomEventMap>(
      event: CustomEventMap[K] | UIEvent,
    ): void;
  }

  interface Window {
    spaNavigate(url: URL, isBack?: boolean): void;
    addCleanup(callback: (...args: unknown[]) => void): void;
  }
}
