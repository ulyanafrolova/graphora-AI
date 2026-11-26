import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { createBrowserRouter, RouterProvider } from "react-router";

import { makeQueryClient } from "./api/queries";
import { routes } from "./routes";

export function App() {
  const [client] = useState(makeQueryClient);
  const [router] = useState(() => createBrowserRouter(routes));
  return (
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
