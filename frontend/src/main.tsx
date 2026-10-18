import "leaflet/dist/leaflet.css"; // sem isso os tiles ficam desalinhados (context.md §14)
import "@/index.css";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "@/App";
import { ApiErro } from "@/lib/api";
import { AuthProvider } from "@/lib/auth";

// Cada requisição é uma execução da Azure Function: reaproveitar respostas e nunca refazer
// consultas só porque a janela ganhou foco. Mutações invalidam o que mudou.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      refetchOnWindowFocus: false,
      retry: (tentativas, erro) => !(erro instanceof ApiErro && erro.status >= 400 && erro.status < 500) && tentativas < 2,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
