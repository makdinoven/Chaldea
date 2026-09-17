import { createSlice, createAsyncThunk, PayloadAction } from "@reduxjs/toolkit";
import type { RootState } from "../store";
import * as professionsApi from "../../api/professions";
import type {
  Profession,
  CharacterProfession,
  Recipe,
  CraftResult,
  ChooseProfessionResponse,
  ChangeProfessionResponse,
  SharpenInfoResponse,
  SharpenRequest,
  SharpenResult,
  RefineInfo,
  RefineResult,
} from "../../types/professions";
import type {
  SocketInfoResponse,
  InsertGemRequest,
  InsertGemResult,
  ExtractGemRequest,
  ExtractGemResult,
} from "../../types/gems";

// --- State ---

interface CraftingState {
  professions: Profession[];
  professionsLoading: boolean;
  professionsError: string | null;

  characterProfession: CharacterProfession | null;
  characterProfessionLoading: boolean;
  characterProfessionError: string | null;

  recipes: Recipe[];
  recipesLoading: boolean;
  recipesError: string | null;

  craftLoading: boolean;
  craftError: string | null;
  lastCraftResult: CraftResult | null;

  sharpenInfo: SharpenInfoResponse | null;
  sharpenInfoLoading: boolean;
  sharpenLoading: boolean;
  sharpenError: string | null;

  socketInfo: SocketInfoResponse | null;
  socketInfoLoading: boolean;
  socketLoading: boolean;
  socketError: string | null;

  refineInfo: RefineInfo | null;
  refineInfoLoading: boolean;
  refineInfoError: string | null;
  refineLoading: boolean;
  refineError: string | null;
}

const initialState: CraftingState = {
  professions: [],
  professionsLoading: false,
  professionsError: null,

  characterProfession: null,
  characterProfessionLoading: false,
  characterProfessionError: null,

  recipes: [],
  recipesLoading: false,
  recipesError: null,

  craftLoading: false,
  craftError: null,
  lastCraftResult: null,

  sharpenInfo: null,
  sharpenInfoLoading: false,
  sharpenLoading: false,
  sharpenError: null,

  socketInfo: null,
  socketInfoLoading: false,
  socketLoading: false,
  socketError: null,

  refineInfo: null,
  refineInfoLoading: false,
  refineInfoError: null,
  refineLoading: false,
  refineError: null,
};

// --- Async Thunks ---

export const fetchProfessions = createAsyncThunk<
  Profession[],
  void,
  { rejectValue: string }
>("crafting/fetchProfessions", async (_, thunkAPI) => {
  try {
    return await professionsApi.fetchProfessions();
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Не удалось загрузить профессии";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const fetchCharacterProfession = createAsyncThunk<
  CharacterProfession,
  number,
  { rejectValue: string }
>("crafting/fetchCharacterProfession", async (characterId, thunkAPI) => {
  try {
    return await professionsApi.fetchCharacterProfession(characterId);
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Не удалось загрузить профессию персонажа";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const chooseProfession = createAsyncThunk<
  ChooseProfessionResponse,
  { characterId: number; professionId: number },
  { rejectValue: string }
>("crafting/chooseProfession", async ({ characterId, professionId }, thunkAPI) => {
  try {
    return await professionsApi.chooseProfession(characterId, {
      profession_id: professionId,
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Не удалось выбрать профессию";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const changeProfession = createAsyncThunk<
  ChangeProfessionResponse,
  { characterId: number; professionId: number },
  { rejectValue: string }
>("crafting/changeProfession", async ({ characterId, professionId }, thunkAPI) => {
  try {
    return await professionsApi.changeProfession(characterId, {
      profession_id: professionId,
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Не удалось сменить профессию";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const fetchRecipes = createAsyncThunk<
  Recipe[],
  { characterId: number; professionId?: number },
  { rejectValue: string }
>("crafting/fetchRecipes", async ({ characterId, professionId }, thunkAPI) => {
  try {
    return await professionsApi.fetchRecipes(characterId, professionId);
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Не удалось загрузить рецепты";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const craftItem = createAsyncThunk<
  CraftResult,
  { characterId: number; recipeId: number },
  { rejectValue: string }
>("crafting/craftItem", async ({ characterId, recipeId }, thunkAPI) => {
  try {
    return await professionsApi.craftItem(characterId, {
      recipe_id: recipeId,
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Не удалось создать предмет";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const fetchSharpenInfo = createAsyncThunk<
  SharpenInfoResponse,
  { characterId: number; itemRowId: number; source?: string },
  { rejectValue: string }
>("crafting/fetchSharpenInfo", async ({ characterId, itemRowId, source }, thunkAPI) => {
  try {
    return await professionsApi.fetchSharpenInfo(characterId, itemRowId, source);
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Не удалось загрузить информацию о заточке";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const sharpenItem = createAsyncThunk<
  SharpenResult,
  { characterId: number; payload: SharpenRequest },
  { rejectValue: string }
>("crafting/sharpenItem", async ({ characterId, payload }, thunkAPI) => {
  try {
    return await professionsApi.sharpenItem(characterId, payload);
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Не удалось заточить предмет";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const fetchSocketInfo = createAsyncThunk<
  SocketInfoResponse,
  { characterId: number; itemRowId: number; source?: string },
  { rejectValue: string }
>("crafting/fetchSocketInfo", async ({ characterId, itemRowId, source }, thunkAPI) => {
  try {
    return await professionsApi.fetchSocketInfo(characterId, itemRowId, source);
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Не удалось загрузить информацию о слотах";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const insertGem = createAsyncThunk<
  InsertGemResult,
  { characterId: number; payload: InsertGemRequest },
  { rejectValue: string }
>("crafting/insertGem", async ({ characterId, payload }, thunkAPI) => {
  try {
    return await professionsApi.insertGem(characterId, payload);
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Не удалось вставить камень";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const extractGem = createAsyncThunk<
  ExtractGemResult,
  { characterId: number; payload: ExtractGemRequest },
  { rejectValue: string }
>("crafting/extractGem", async ({ characterId, payload }, thunkAPI) => {
  try {
    return await professionsApi.extractGem(characterId, payload);
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Не удалось извлечь камень";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const fetchRefineInfo = createAsyncThunk<
  RefineInfo,
  number,
  { rejectValue: string }
>("crafting/fetchRefineInfo", async (characterId, thunkAPI) => {
  try {
    return await professionsApi.fetchRefineInfo(characterId);
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Не удалось загрузить данные переработки";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const refineItem = createAsyncThunk<
  RefineResult,
  { characterId: number; sourceItemId: number; quantity: number },
  { rejectValue: string }
>("crafting/refineItem", async ({ characterId, sourceItemId, quantity }, thunkAPI) => {
  try {
    return await professionsApi.refineItem(characterId, {
      source_item_id: sourceItemId,
      quantity,
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Не удалось переработать";
    return thunkAPI.rejectWithValue(msg);
  }
});

// --- Slice ---

const craftingSlice = createSlice({
  name: "crafting",
  initialState,
  reducers: {
    clearCraftResult(state) {
      state.lastCraftResult = null;
      state.craftError = null;
    },
    clearCharacterProfession(state) {
      state.characterProfession = null;
      state.characterProfessionError = null;
    },
    clearRecipes(state) {
      state.recipes = [];
      state.recipesError = null;
    },
    clearSharpenInfo(state) {
      state.sharpenInfo = null;
      state.sharpenError = null;
    },
    clearSocketInfo(state) {
      state.socketInfo = null;
      state.socketError = null;
    },
    clearRefineInfo(state) {
      state.refineInfo = null;
      state.refineInfoError = null;
      state.refineError = null;
    },
  },
  extraReducers: (builder) => {
    // fetchProfessions
    builder
      .addCase(fetchProfessions.pending, (state) => {
        state.professionsLoading = true;
        state.professionsError = null;
      })
      .addCase(fetchProfessions.fulfilled, (state, action: PayloadAction<Profession[]>) => {
        state.professionsLoading = false;
        state.professions = action.payload;
      })
      .addCase(fetchProfessions.rejected, (state, action) => {
        state.professionsLoading = false;
        state.professionsError = action.payload ?? "Произошла ошибка";
      });

    // fetchCharacterProfession
    builder
      .addCase(fetchCharacterProfession.pending, (state) => {
        state.characterProfessionLoading = true;
        state.characterProfessionError = null;
      })
      .addCase(
        fetchCharacterProfession.fulfilled,
        (state, action: PayloadAction<CharacterProfession>) => {
          state.characterProfessionLoading = false;
          state.characterProfession = action.payload;
        },
      )
      .addCase(fetchCharacterProfession.rejected, (state, action) => {
        state.characterProfessionLoading = false;
        // 404 means no profession chosen yet — not an error for UI
        state.characterProfession = null;
        state.characterProfessionError = action.payload ?? "Произошла ошибка";
      });

    // chooseProfession
    builder
      .addCase(chooseProfession.pending, (state) => {
        state.characterProfessionLoading = true;
        state.characterProfessionError = null;
      })
      .addCase(chooseProfession.fulfilled, (state) => {
        state.characterProfessionLoading = false;
        // Refetch character profession to get full data
      })
      .addCase(chooseProfession.rejected, (state, action) => {
        state.characterProfessionLoading = false;
        state.characterProfessionError = action.payload ?? "Произошла ошибка";
      });

    // changeProfession
    builder
      .addCase(changeProfession.pending, (state) => {
        state.characterProfessionLoading = true;
        state.characterProfessionError = null;
      })
      .addCase(changeProfession.fulfilled, (state) => {
        state.characterProfessionLoading = false;
        // Refetch character profession to get full data
      })
      .addCase(changeProfession.rejected, (state, action) => {
        state.characterProfessionLoading = false;
        state.characterProfessionError = action.payload ?? "Произошла ошибка";
      });

    // fetchRecipes
    builder
      .addCase(fetchRecipes.pending, (state) => {
        state.recipesLoading = true;
        state.recipesError = null;
      })
      .addCase(fetchRecipes.fulfilled, (state, action: PayloadAction<Recipe[]>) => {
        state.recipesLoading = false;
        state.recipes = action.payload;
      })
      .addCase(fetchRecipes.rejected, (state, action) => {
        state.recipesLoading = false;
        state.recipesError = action.payload ?? "Произошла ошибка";
      });

    // craftItem
    builder
      .addCase(craftItem.pending, (state) => {
        state.craftLoading = true;
        state.craftError = null;
        state.lastCraftResult = null;
      })
      .addCase(craftItem.fulfilled, (state, action: PayloadAction<CraftResult>) => {
        state.craftLoading = false;
        state.lastCraftResult = action.payload;
      })
      .addCase(craftItem.rejected, (state, action) => {
        state.craftLoading = false;
        state.craftError = action.payload ?? "Произошла ошибка";
      });

    // fetchSharpenInfo
    builder
      .addCase(fetchSharpenInfo.pending, (state) => {
        state.sharpenInfoLoading = true;
        state.sharpenError = null;
      })
      .addCase(fetchSharpenInfo.fulfilled, (state, action: PayloadAction<SharpenInfoResponse>) => {
        state.sharpenInfoLoading = false;
        state.sharpenInfo = action.payload;
      })
      .addCase(fetchSharpenInfo.rejected, (state, action) => {
        state.sharpenInfoLoading = false;
        state.sharpenError = action.payload ?? "Произошла ошибка";
      });

    // sharpenItem
    builder
      .addCase(sharpenItem.pending, (state) => {
        state.sharpenLoading = true;
        state.sharpenError = null;
      })
      .addCase(sharpenItem.fulfilled, (state) => {
        state.sharpenLoading = false;
      })
      .addCase(sharpenItem.rejected, (state, action) => {
        state.sharpenLoading = false;
        state.sharpenError = action.payload ?? "Произошла ошибка";
      });

    // fetchSocketInfo
    builder
      .addCase(fetchSocketInfo.pending, (state) => {
        state.socketInfoLoading = true;
        state.socketError = null;
      })
      .addCase(fetchSocketInfo.fulfilled, (state, action: PayloadAction<SocketInfoResponse>) => {
        state.socketInfoLoading = false;
        state.socketInfo = action.payload;
      })
      .addCase(fetchSocketInfo.rejected, (state, action) => {
        state.socketInfoLoading = false;
        state.socketError = action.payload ?? "Произошла ошибка";
      });

    // insertGem
    builder
      .addCase(insertGem.pending, (state) => {
        state.socketLoading = true;
        state.socketError = null;
      })
      .addCase(insertGem.fulfilled, (state) => {
        state.socketLoading = false;
      })
      .addCase(insertGem.rejected, (state, action) => {
        state.socketLoading = false;
        state.socketError = action.payload ?? "Произошла ошибка";
      });

    // extractGem
    builder
      .addCase(extractGem.pending, (state) => {
        state.socketLoading = true;
        state.socketError = null;
      })
      .addCase(extractGem.fulfilled, (state) => {
        state.socketLoading = false;
      })
      .addCase(extractGem.rejected, (state, action) => {
        state.socketLoading = false;
        state.socketError = action.payload ?? "Произошла ошибка";
      });

    // fetchRefineInfo
    builder
      .addCase(fetchRefineInfo.pending, (state) => {
        state.refineInfoLoading = true;
        state.refineInfoError = null;
      })
      .addCase(fetchRefineInfo.fulfilled, (state, action: PayloadAction<RefineInfo>) => {
        state.refineInfoLoading = false;
        state.refineInfo = action.payload;
      })
      .addCase(fetchRefineInfo.rejected, (state, action) => {
        state.refineInfoLoading = false;
        state.refineInfoError = action.payload ?? "Произошла ошибка";
      });

    // refineItem
    builder
      .addCase(refineItem.pending, (state) => {
        state.refineLoading = true;
        state.refineError = null;
      })
      .addCase(refineItem.fulfilled, (state) => {
        state.refineLoading = false;
      })
      .addCase(refineItem.rejected, (state, action) => {
        state.refineLoading = false;
        state.refineError = action.payload ?? "Произошла ошибка";
      });
  },
});

export const {
  clearCraftResult,
  clearCharacterProfession,
  clearRecipes,
  clearSharpenInfo,
  clearSocketInfo,
  clearRefineInfo,
} = craftingSlice.actions;

// --- Selectors ---

export const selectProfessions = (state: RootState) => state.crafting.professions;
export const selectProfessionsLoading = (state: RootState) => state.crafting.professionsLoading;
export const selectProfessionsError = (state: RootState) => state.crafting.professionsError;

export const selectCharacterProfession = (state: RootState) =>
  state.crafting.characterProfession;
export const selectCharacterProfessionLoading = (state: RootState) =>
  state.crafting.characterProfessionLoading;
export const selectCharacterProfessionError = (state: RootState) =>
  state.crafting.characterProfessionError;

export const selectRecipes = (state: RootState) => state.crafting.recipes;
export const selectRecipesLoading = (state: RootState) => state.crafting.recipesLoading;
export const selectRecipesError = (state: RootState) => state.crafting.recipesError;

export const selectCraftLoading = (state: RootState) => state.crafting.craftLoading;
export const selectCraftError = (state: RootState) => state.crafting.craftError;
export const selectLastCraftResult = (state: RootState) => state.crafting.lastCraftResult;

export const selectSharpenInfo = (state: RootState) => state.crafting.sharpenInfo;
export const selectSharpenInfoLoading = (state: RootState) => state.crafting.sharpenInfoLoading;
export const selectSharpenLoading = (state: RootState) => state.crafting.sharpenLoading;
export const selectSharpenError = (state: RootState) => state.crafting.sharpenError;

export const selectSocketInfo = (state: RootState) => state.crafting.socketInfo;
export const selectSocketInfoLoading = (state: RootState) => state.crafting.socketInfoLoading;
export const selectSocketLoading = (state: RootState) => state.crafting.socketLoading;
export const selectSocketError = (state: RootState) => state.crafting.socketError;

export const selectRefineInfo = (state: RootState) => state.crafting.refineInfo;
export const selectRefineInfoLoading = (state: RootState) => state.crafting.refineInfoLoading;
export const selectRefineInfoError = (state: RootState) => state.crafting.refineInfoError;
export const selectRefineLoading = (state: RootState) => state.crafting.refineLoading;
export const selectRefineError = (state: RootState) => state.crafting.refineError;

export default craftingSlice.reducer;
