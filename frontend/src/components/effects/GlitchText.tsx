import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

export const GlitchText = ({ text }: { text: string }) => {
  const [isGlitching, setIsGlitching] = useState(false);

  useEffect(() => {
    const glitchInterval = setInterval(() => {
      if (Math.random() > 0.95) {
        setIsGlitching(true);
        setTimeout(() => setIsGlitching(false), 50 + Math.random() * 150);
      }
    }, 2000);
    return () => clearInterval(glitchInterval);
  }, []);

  return (
    <span className="relative inline-block">
      <span className={isGlitching ? "opacity-0" : "opacity-100"}>{text}</span>
      {isGlitching && (
        <>
          <span className="absolute top-0 left-[2px] text-red-500 opacity-70 mix-blend-screen">{text}</span>
          <span className="absolute top-0 -left-[2px] text-blue-500 opacity-70 mix-blend-screen">{text}</span>
          <span className="absolute top-0 left-0 text-white truncate w-full h-[50%] overflow-hidden translate-x-[5px]">{text}</span>
        </>
      )}
    </span>
  );
};

export const ScanlineReveal = ({ children, isVisible }: { children: React.ReactNode, isVisible: boolean }) => {
  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.5, ease: "easeInOut" }}
          className="overflow-hidden"
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  );
};
