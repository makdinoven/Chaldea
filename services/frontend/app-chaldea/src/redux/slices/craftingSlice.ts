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
  LearnRecipeResponse,
  ExtractInfoResponse,
  ExtractEssenceResult,
  TransmuteInfoResponse,
  TransmuteResult,
  SharpenInfoResponse,
  SharpenRequest,
  SharpenResult,
} from "../../types/professions";
import type {
  SocketInfoResponse,
  InsertGemRequest,
  InsertGemResult,
  ExtractGemRequest,
  ExtractGemResult,
  SmeltInfoResponse,
  SmeltRequest,
  SmeltResult,
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

  extractInfo: ExtractInfoResponse | null;
  extractInfoLoading: boolean;
  extractLoading: boolean;
  extractError: string | null;

  transmuteInfo: TransmuteInfoResponse | null;
  transmuteInfoLoading: boolean;
  transmuteLoading: boolean;
  transmuteError: string | null;

  sharpenInfo: SharpenInfoResponse | null;
  sharpenInfoLoading: boolean;
  sharpenLoading: boolean;
  sharpenError: string | null;

  socketInfo: SocketInfoResponse | null;
  socketInfoLoading: boolean;
  socketLoading: boolean;
  socketError: string | null;

  smeltInfo: SmeltInfoResponse | null;
  smeltInfoLoading: boolean;
  smeltLoading: boolean;
  smeltError: string | null;
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

  extractInfo: null,
  extractInfoLoading: false,
  extractLoading: false,
  extractError: null,

  transmuteInfo: null,
  transmuteInfoLoading: false,
  transmuteLoading: false,
  transmuteError: null,

  sharpenInfo: null,
  sharpenInfoLoading: false,
  sharpenLoading: false,
  sharpenError: null,

  socketInfo: null,
  socketInfoLoading: false,
  socketLoading: false,
  socketError: null,

  smeltInfo: null,
  smeltInfoLoading: false,
  smeltLoading: false,
  smeltError: null,
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
  { characterId: number; recipeId: number; blueprintItemId?: number | null },
  { rejectValue: string }
>("crafting/craftItem", async ({ characterId, recipeId, blueprintItemId }, thunkAPI) => {
  try {
    return await professionsApi.craftItem(characterId, {
      recipe_id: recipeId,
      blueprint_item_id: blueprintItemId ?? null,
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Не удалось создать предмет";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const learnRecipe = createAsyncThunk<
  LearnRecipeResponse,
  { characterId: number; recipeId: number },
  { rejectValue: string }
>("crafting/learnRecipe", async ({ characterId, recipeId }, thunkAPI) => {
  try {
    return await professionsApi.learnRecipe(characterId, {
      recipe_id: recipeId,
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Не удалось выучить рецепт";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const fetchExtractInfo = createAsyncThunk<
  ExtractInfoResponse,
  number,
  { rejectValue: string }
>("crafting/fetchExtractInfo", async (characterId, thunkAPI) => {
  try {
    return await professionsApi.fetchExtractInfo(characterId);
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Не удалось загрузить информацию об экстракции";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const extractEssence = createAsyncThunk<
  ExtractEssenceResult,
  { characterId: number; crystalItemId: number },
  { rejectValue: string }
>("crafting/extractEssence", async ({ characterId, crystalItemId }, thunkAPI) => {
  try {
    return await professionsApi.extractEssence(characterId, crystalItemId);
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Не удалось извлечь эссенцию";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const fetchTransmuteInfo = createAsyncThunk<
  TransmuteInfoResponse,
  number,
  { rejectValue: string }
>("crafting/fetchTransmuteInfo", async (characterId, thunkAPI) => {
  try {
    return await professionsApi.fetchTransmuteInfo(characterId);
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Не удалось загрузить информацию о трансмутации";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const transmuteItem = createAsyncThunk<
  TransmuteResult,
  { characterId: number; inventoryItemId: number },
  { rejectValue: string }
>("crafting/transmuteItem", async ({ characterId, inventoryItemId }, thunkAPI) => {
  try {
    return await professionsApi.transmuteItem(characterId, inventoryItemId);
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Не удалось трансмутировать ресурс";
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

export const fetchSmeltInfo = createAsyncThunk<
  SmeltInfoResponse,
  { characterId: number; itemRowId: number },
  { rejectValue: string }
>("crafting/fetchSmeltInfo", async ({ characterId, itemRowId }, thunkAPI) => {
  try {
    return await professionsApi.fetchSmeltInfo(characterId, itemRowId);
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Не удалось загрузить информацию о переплавке";
    return thunkAPI.rejectWithValue(msg);
  }
});

export const smeltItem = createAsyncThunk<
  SmeltResult,
  { characterId: number; payload: SmeltRequest },
  { rejectValue: string }
>("crafting/smeltItem", async ({ characterId, payload }, thunkAPI) => {
  try {
    return await professionsApi.smeltItem(characterId, payload);
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Не удалось переплавить предмет";
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
    clearExtractInfo(state) {
      state.extractInfo = null;
      state.extractError = null;
    },
    clearTransmuteInfo(state) {
      state.transmuteInfo = null;
      state.transmuteError = null;
    },
    clearSharpenInfo(state) {
      state.sharpenInfo = null;
      state.sharpenError = null;
    },
    clearSocketInfo(state) {
      state.socketInfo = null;
      state.socketError = null;
    },
    clearSmeltInfo(state) {
      state.smeltInfo = null;
      state.smeltError = null;
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

    // learnRecipe
    builder
      .addCase(learnRecipe.pending, (state) => {
        state.recipesLoading = true;
        state.recipesError = null;
      })
      .addCase(learnRecipe.fulfilled, (state) => {
        state.recipesLoading = false;
        // Recipes list should be refetched after learning
      })
      .addCase(learnRecipe.rejected, (state, action) => {
        state.recipesLoading = false;
        state.recipesError = action.payload ?? "Произошла ошибка";
      });

    // fetchExtractInfo
    builder
      .addCase(fetchExtractInfo.pending, (state) => {
        state.extractInfoLoading = true;
        state.extractError = null;
      })
      .addCase(fetchExtractInfo.fulfilled, (state, action: PayloadAction<ExtractInfoResponse>) => {
        state.extractInfoLoading = false;
        state.extractInfo = action.payload;
      })
      .addCase(fetchExtractInfo.rejected, (state, action) => {
        state.extractInfoLoading = false;
        state.extractError = action.payload ?? "Произошла ошибка";
      });

    // extractEssence
    builder
      .addCase(extractEssence.pending, (state) => {
        state.extractLoading = true;
        state.extractError = null;
      })
      .addCase(extractEssence.fulfilled, (state) => {
        state.extractLoading = false;
      })
      .addCase(extractEssence.rejected, (state, action) => {
        state.extractLoading = false;
        state.extractError = action.payload ?? "Произошла ошибка";
      });

    // fetchTransmuteInfo
    builder
      .addCase(fetchTransmuteInfo.pending, (state) => {
        state.transmuteInfoLoading = true;
        state.transmuteError = null;
      })
      .addCase(fetchTransmuteInfo.fulfilled, (state, action: PayloadAction<TransmuteInfoResponse>) => {
        state.transmuteInfoLoading = false;
        state.transmuteInfo = action.payload;
      })
      .addCase(fetchTransmuteInfo.rejected, (state, action) => {
        state.transmuteInfoLoading = false;
        state.transmuteError = action.payload ?? "Произошла ошибка";
      });

    // transmuteItem
    builder
      .addCase(transmuteItem.pending, (state) => {
        state.transmuteLoading = true;
        state.transmuteError = null;
      })
      .addCase(transmuteItem.fulfilled, (state) => {
        state.transmuteLoading = false;
      })
      .addCase(transmuteItem.rejected, (state, action) => {
        state.transmuteLoading = false;
        state.transmuteError = action.payload ?? "Произошла ошибка";
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

    // fetchSmeltInfo
    builder
      .addCase(fetchSmeltInfo.pending, (state) => {
        state.smeltInfoLoading = true;
        state.smeltError = null;
      })
      .addCase(fetchSmeltInfo.fulfilled, (state, action: PayloadAction<SmeltInfoResponse>) => {
        state.smeltInfoLoading = false;
        state.smeltInfo = action.payload;
      })
      .addCase(fetchSmeltInfo.rejected, (state, action) => {
        state.smeltInfoLoading = false;
        state.smeltError = action.payload ?? "Произошла ошибка";
      });

    // smeltItem
    builder
      .addCase(smeltItem.pending, (state) => {
        state.smeltLoading = true;
        state.smeltError = null;
      })
      .addCase(smeltItem.fulfilled, (state) => {
        state.smeltLoading = false;
      })
      .addCase(smeltItem.rejected, (state, action) => {
        state.smeltLoading = false;
        state.smeltError = action.payload ?? "Произошла ошибка";
      });
  },
});

export const {
  clearCraftResult,
  clearCharacterProfession,
  clearRecipes,
  clearExtractInfo,
  clearTransmuteInfo,
  clearSharpenInfo,
  clearSocketInfo,
  clearSmeltInfo,
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

export const selectExtractInfo = (state: RootState) => state.crafting.extractInfo;
export const selectExtractInfoLoading = (state: RootState) => state.crafting.extractInfoLoading;
export const selectExtractLoading = (state: RootState) => state.crafting.extractLoading;
export const selectExtractError = (state: RootState) => state.crafting.extractError;

export const selectTransmuteInfo = (state: RootState) => state.crafting.transmuteInfo;
export const selectTransmuteInfoLoading = (state: RootState) => state.crafting.transmuteInfoLoading;
export const selectTransmuteLoading = (state: RootState) => state.crafting.transmuteLoading;
export const selectTransmuteError = (state: RootState) => state.crafting.transmuteError;

export const selectSharpenInfo = (state: RootState) => state.crafting.sharpenInfo;
export const selectSharpenInfoLoading = (state: RootState) => state.crafting.sharpenInfoLoading;
export const selectSharpenLoading = (state: RootState) => state.crafting.sharpenLoading;
export const selectSharpenError = (state: RootState) => state.crafting.sharpenError;

export const selectSocketInfo = (state: RootState) => state.crafting.socketInfo;
export const selectSocketInfoLoading = (state: RootState) => state.crafting.socketInfoLoading;
export const selectSocketLoading = (state: RootState) => state.crafting.socketLoading;
export const selectSocketError = (state: RootState) => state.crafting.socketError;

export const selectSmeltInfo = (state: RootState) => state.crafting.smeltInfo;
export const selectSmeltInfoLoading = (state: RootState) => state.crafting.smeltInfoLoading;
export const selectSmeltLoading = (state: RootState) => state.crafting.smeltLoading;
export const selectSmeltError = (state: RootState) => state.crafting.smeltError;

export default craftingSlice.reducer;
