import { act, renderHook, waitFor } from "@testing-library/react";
import { SWRConfig } from "swr";
import { useServerPaginatedTable } from "./useServerPaginatedTable";

interface Row {
  id: number;
}

const PAGE_SIZE = 20;

function makeLoader() {
  return jest.fn(
    async ({
      offset,
      limit,
      q,
    }: {
      offset: number;
      limit: number;
      q: string;
    }) => ({
      items: [{ id: offset }],
      total: 42 + q.length,
    })
  );
}

function renderTable(
  requestKey: string,
  loader: ReturnType<typeof makeLoader>
) {
  return renderHook(
    (key: string) =>
      useServerPaginatedTable<Row>({
        requestKey: key,
        pageSize: PAGE_SIZE,
        loader,
      }),
    {
      initialProps: requestKey,
      wrapper: ({ children }) => (
        <SWRConfig value={{ provider: () => new Map() }}>{children}</SWRConfig>
      ),
    }
  );
}

describe("useServerPaginatedTable", () => {
  test("loads the first page on mount", async () => {
    const loader = makeLoader();
    const { result } = renderTable("key-a", loader);

    await waitFor(() => expect(result.current.serverSide.totalItems).toBe(42));
    expect(loader).toHaveBeenCalledWith({
      offset: 0,
      limit: PAGE_SIZE,
      q: "",
    });
    expect(result.current.rows).toEqual([{ id: 0 }]);
  });

  test("pagination requests the matching offset", async () => {
    const loader = makeLoader();
    const { result } = renderTable("key-a", loader);

    await waitFor(() => expect(loader).toHaveBeenCalled());

    act(() => {
      result.current.serverSide.onPaginationChange(1, PAGE_SIZE);
    });

    await waitFor(() =>
      expect(loader).toHaveBeenLastCalledWith({
        offset: PAGE_SIZE,
        limit: PAGE_SIZE,
        q: "",
      })
    );
  });

  test("search debounces and resets to the first page", async () => {
    jest.useFakeTimers();
    try {
      const loader = makeLoader();
      const { result } = renderHook(
        () =>
          useServerPaginatedTable<Row>({
            requestKey: "key-a",
            pageSize: PAGE_SIZE,
            loader,
          }),
        {
          wrapper: ({ children }) => (
            <SWRConfig value={{ provider: () => new Map() }}>
              {children}
            </SWRConfig>
          ),
        }
      );

      await act(async () => {
        await jest.advanceTimersByTimeAsync(400);
      });
      expect(loader).toHaveBeenCalledTimes(1);

      // Move to page 2 first so the reset is observable.
      act(() => {
        result.current.serverSide.onPaginationChange(1, PAGE_SIZE);
      });
      await act(async () => {
        await jest.advanceTimersByTimeAsync(400);
      });
      expect(loader).toHaveBeenLastCalledWith({
        offset: PAGE_SIZE,
        limit: PAGE_SIZE,
        q: "",
      });

      act(() => {
        result.current.searchInputProps.onChange({
          target: { value: "hello" },
        } as React.ChangeEvent<HTMLInputElement>);
      });

      // Before the debounce elapses, no new request fires.
      await act(async () => {
        await jest.advanceTimersByTimeAsync(100);
      });
      expect(loader).toHaveBeenCalledTimes(2);

      await act(async () => {
        await jest.advanceTimersByTimeAsync(400);
      });
      await waitFor(() =>
        expect(loader).toHaveBeenLastCalledWith({
          offset: 0,
          limit: PAGE_SIZE,
          q: "hello",
        })
      );
      expect(result.current.searchTerm).toBe("hello");
    } finally {
      jest.useRealTimers();
    }
  });

  test("changing the request key resets to the first page", async () => {
    const loader = makeLoader();
    const { result, rerender } = renderTable("key-a", loader);

    await waitFor(() => expect(loader).toHaveBeenCalled());
    act(() => {
      result.current.serverSide.onPaginationChange(1, PAGE_SIZE);
    });
    await waitFor(() =>
      expect(loader).toHaveBeenLastCalledWith({
        offset: PAGE_SIZE,
        limit: PAGE_SIZE,
        q: "",
      })
    );

    rerender("key-b");

    await waitFor(() =>
      expect(loader).toHaveBeenLastCalledWith({
        offset: 0,
        limit: PAGE_SIZE,
        q: "",
      })
    );
  });

  test("disabled tables never call the loader", async () => {
    const loader = makeLoader();
    renderHook(() =>
      useServerPaginatedTable<Row>({
        requestKey: "key-a",
        pageSize: PAGE_SIZE,
        enabled: false,
        loader,
      })
    );

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });
    expect(loader).not.toHaveBeenCalled();
  });
});
